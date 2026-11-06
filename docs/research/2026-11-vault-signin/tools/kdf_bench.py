"""Time scrypt (the vault default) against Argon2id on this machine, median of 5.

usage: kdf_bench.py   (prints JSON; random inputs, no secret; one machine, not a general claim)
"""
import time, os, statistics, json
import cryptography
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
pw = os.urandom(24); salt = os.urandom(16)
def t(f, n=5):
    xs=[]
    for _ in range(n):
        s=time.perf_counter(); f(); xs.append(time.perf_counter()-s)
    return round(statistics.median(xs)*1000), round(max(xs)*1000)
res = {"cryptography": cryptography.__version__}
from cryptography.hazmat.backends.openssl.backend import backend
res["openssl"] = backend.openssl_version_text()
res["scrypt_2^17_r8_p1_ms(median,max)"] = t(lambda: Scrypt(salt=salt,length=32,n=2**17,r=8,p=1).derive(pw))
for name,(m,i,l) in {"argon2id_owasp_min_19MiB_t2_p1":(19*1024,2,1),"argon2id_rfc9106_low_64MiB_t3_p4":(64*1024,3,4),"argon2id_128MiB_t3_p4":(128*1024,3,4)}.items():
    res[name+"_ms(median,max)"] = t(lambda: Argon2id(salt=salt,length=32,iterations=i,lanes=l,memory_cost=m).derive(pw))
print(json.dumps(res, indent=1))
