from urlparse import urlparse
from multiprocessing import Process, Queue, Value
import httplib, sys, urllib
import json
from oscrypto import asymmetric
from ocspbuilder import OCSPRequestBuilder
from asn1crypto import core, ocsp
import base64
import time

workers = 16
outfile = './OCSP_revoked/certs'
infile = '../certs_without_crl.json'

issuerCerts = {}
issuer1 = open('lets-encrypt-x1-cross-signed.pem').read()
issuer2 = open('lets-encrypt-x2-cross-signed.pem').read()
issuer3 = open('lets-encrypt-x3-cross-signed.pem').read()
issuer4 = open('lets-encrypt-x4-cross-signed.pem').read()
issuerCerts = {}
issuerCerts['http://ocsp.int-x1.letsencrypt.org'] = asymmetric.load_certificate(issuer1)
issuerCerts['http://ocsp.int-x2.letsencrypt.org'] = asymmetric.load_certificate(issuer2)
issuerCerts['http://ocsp.int-x3.letsencrypt.org'] = asymmetric.load_certificate(issuer3)
issuerCerts['http://ocsp.int-x4.letsencrypt.org'] = asymmetric.load_certificate(issuer4)

def doWork(i, q, check_finish):
    print('starting worker ' + str(i))
    out = open(outfile + str(i) + '.json', 'w')
    while True:
        try:
            if check_finish.value and q.empty():
                break
            cert = json.loads(q.get(timeout=1))
            if(cert['parsed']['extensions']['authority_info_access']['ocsp_urls']):
                urlList = cert['parsed']['extensions']['authority_info_access']['ocsp_urls']
                url = urlList[0].rstrip('/').lstrip(' ')
                if(issuerCerts.get(url)): # only check if we have the issuer cert
                    if(isRevoked(url, cert['raw'])):
                        out.write(json.dumps(cert) + '\n')
        except:
            pass
    print("worker %d exit" %i)

def isRevoked(url, rawCert):
    subject_cert = asymmetric.load_certificate(base64.b64decode(rawCert))
    builder = OCSPRequestBuilder(subject_cert, issuerCerts[url])
    ocsp_request = builder.build()
    url = urlparse(url)
    headers = {}
    conn = httplib.HTTPConnection(url.netloc)
    conn.request("POST", url.path, ocsp_request.dump(), headers)
    res = conn.getresponse().read()
    ocspResponseClass = ocsp.OCSPResponse.load(res)
    return (ocspResponseClass.response_data['responses'][0]['cert_status'].name != 'good')

if __name__ == '__main__':
    q = Queue(workers * 16)
    check_finish = Value('i', 0)
    for i in range(workers):
        p = Process(target=doWork, args=(i, q, check_finish))
        p.start()
    try:
        ctr = 0
        for cert in open(infile, 'r'):
            q.put(cert)
            ctr += 1
            if(ctr % 10000 == 0):
                print(str(ctr) + " certificates processed")
        check_finish.value = 1
        print("End of put certificates into queue")
    except KeyboardInterrupt:
        sys.exit(1)
