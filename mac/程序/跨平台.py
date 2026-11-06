"""Mac 和 Windows 不一样的地方都放这里（只用 Python 标准库）。
- 找电脑名字和局域网地址、打开文件夹、放剪贴板、移到回收站、找相机卡；
- 手机通道要的 https 证书：Windows 没有 openssl，所以用纯 Python 生成，两边走同一条路。"""
import base64,datetime,hashlib,json,os,re,secrets,socket,string,subprocess,tempfile
from pathlib import Path
WIN=os.name=='nt'
HIDDEN=0x08000000 if WIN else 0
def host_name():
 """手机用这个名字找到电脑。Windows 上名字不一定找得到，手机网址会把 IP 排在前面。"""
 if not WIN:
  try:return subprocess.check_output(['/usr/sbin/scutil','--get','LocalHostName'],text=True,stderr=subprocess.DEVNULL).strip()+'.local'
  except (OSError,subprocess.CalledProcessError):pass
 return (socket.gethostname().split('.')[0] or 'localhost')+'.local'
def lan_ips():
 out=[]
 def add(ip):
  if ip and ip not in out and not ip.startswith(('127.','169.254.','0.')):out.append(ip)
 if not WIN:
  for iface in ('en0','en1','en2'):
   try:add(subprocess.run(['/usr/sbin/ipconfig','getifaddr',iface],capture_output=True,text=True).stdout.strip())
   except OSError:pass
 try:   # 不会真的发数据，只是让系统选一张能出去的网卡
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
   s.connect(('10.255.255.255',1));add(s.getsockname()[0])
 except OSError:pass
 try:
  for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):add(info[4][0])
 except OSError:pass
 return out
def lan_ip():
 ips=lan_ips();return ips[0] if ips else None
def open_path(path):
 if WIN:os.startfile(str(path))
 else:subprocess.run(['/usr/bin/open',str(path)],check=False,timeout=10)
def reveal(path):
 if WIN:subprocess.run(['explorer','/select,',str(path)],check=False,timeout=10)
 else:subprocess.run(['/usr/bin/open','-R',str(path)],check=False,timeout=10)
def _powershell(script,data):
 """中文走 UTF-8 编码的环境变量，不经过命令行，免得乱码。"""
 env=dict(os.environ,CODA_DATA=base64.b64encode(json.dumps(data,ensure_ascii=False).encode('utf-8')).decode('ascii'))
 head='$d=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:CODA_DATA))|ConvertFrom-Json;'
 return subprocess.run(['powershell','-NoProfile','-NonInteractive','-STA','-ExecutionPolicy','Bypass','-Command',head+script],capture_output=True,text=True,timeout=60,env=env,creationflags=HIDDEN)
COPY_PS=('Add-Type -AssemblyName System.Windows.Forms;$o=New-Object System.Windows.Forms.DataObject;'
 'if($d.text){$o.SetText([string]$d.text)};'
 'if($d.files.Count -gt 0){$c=New-Object System.Collections.Specialized.StringCollection;foreach($f in $d.files){[void]$c.Add([string]$f)};$o.SetFileDropList($c)};'
 '[System.Windows.Forms.Clipboard]::SetDataObject($o,$true);Write-Output ok')
def copy_windows(files,text=''):
 r=_powershell(COPY_PS,{'files':[str(f) for f in files],'text':text})
 if r.stdout.strip()!='ok':raise ValueError('没能放到剪贴板：'+(r.stderr.strip()[-200:] or '未知原因'))
TRASH_PS=('Add-Type -AssemblyName Microsoft.VisualBasic;$n=0;foreach($f in $d.files){'
 '[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile([string]$f,"OnlyErrorDialogs","SendToRecycleBin");$n++};Write-Output $n')
def trash_windows(paths):
 """移到回收站，还能放回去；不直接删。"""
 r=_powershell(TRASH_PS,{'files':[str(p) for p in paths]})
 try:return int(r.stdout.strip())
 except ValueError:raise ValueError('没能移到回收站：'+(r.stderr.strip()[-200:] or '未知原因'))
def volumes():
 """插着的磁盘：Mac 看 /Volumes，Windows 看 D: 到 Z:。"""
 if WIN:return [Path(c+':\\') for c in string.ascii_uppercase[3:] if os.path.exists(c+':\\')]
 try:return sorted(Path('/Volumes').iterdir())
 except OSError:return []
# ---- 证书：只做手机通道要的这几种，不算通用实现
SMALL=[p for p in range(3,2000) if all(p%q for q in range(3,int(p**.5)+1,2))]
def _prime(bits):
 while True:
  n=secrets.randbits(bits)|(3<<(bits-2))|1
  if any(n%p==0 for p in SMALL):continue
  d,r=n-1,0
  while d%2==0:d//=2;r+=1
  for _ in range(16):
   x=pow(secrets.randbelow(n-3)+2,d,n)
   if x in (1,n-1):continue
   for _ in range(r-1):
    x=x*x%n
    if x==n-1:break
   else:break
  else:return n
def new_key(bits=2048):
 e=65537
 while True:
  p,q=_prime(bits//2),_prime(bits//2)
  if p==q:continue
  if p<q:p,q=q,p
  phi=(p-1)*(q-1)
  if phi%e==0 or (p*q).bit_length()!=bits:continue
  return dict(n=p*q,e=e,d=pow(e,-1,phi),p=p,q=q)
def _len(n):
 if n<128:return bytes([n])
 b=n.to_bytes((n.bit_length()+7)//8,'big');return bytes([0x80|len(b)])+b
def _tlv(tag,body):return bytes([tag])+_len(len(body))+body
def _seq(*x):return _tlv(0x30,b''.join(x))
def _set(*x):return _tlv(0x31,b''.join(x))
def _int(n):
 b=n.to_bytes(n.bit_length()//8+1,'big');return _tlv(2,b)
def _oid(text):
 a=[int(x) for x in text.split('.')];out=bytearray([a[0]*40+a[1]])
 for v in a[2:]:
  chunk=[v&127];v>>=7
  while v:chunk.insert(0,(v&127)|128);v>>=7
  out+=bytes(chunk)
 return _tlv(6,bytes(out))
def _bits(b):return _tlv(3,b'\0'+b)
def _name(cn):return _seq(_set(_seq(_oid('2.5.4.3'),_tlv(12,cn.encode('utf-8')))))
def _time(d):return _tlv(23,d.strftime('%y%m%d%H%M%SZ').encode()) if d.year<2050 else _tlv(24,d.strftime('%Y%m%d%H%M%SZ').encode())
SHA256RSA=_seq(_oid('1.2.840.113549.1.1.11'),_tlv(5,b''))
def _public(k):return _seq(_int(k['n']),_int(k['e']))
def _keyid(k):return hashlib.sha1(_public(k)).digest()
def _ext(oid,value,critical=False):return _seq(_oid(oid),*([_tlv(1,b'\xff')] if critical else []),_tlv(4,value))
def _sign(k,msg):
 digest=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(msg).digest()
 size=(k['n'].bit_length()+7)//8
 em=b'\0\1'+b'\xff'*(size-len(digest)-3)+b'\0'+digest
 return pow(int.from_bytes(em,'big'),k['d'],k['n']).to_bytes(size,'big')
def _pem(label,der):
 body=base64.encodebytes(der).decode('ascii').replace('\n','')
 return '-----BEGIN %s-----\n%s\n-----END %s-----\n'%(label,'\n'.join(body[i:i+64] for i in range(0,len(body),64)),label)
def key_pem(k):
 return _pem('RSA PRIVATE KEY',_seq(_int(0),*[_int(x) for x in (k['n'],k['e'],k['d'],k['p'],k['q'],k['d']%(k['p']-1),k['d']%(k['q']-1),pow(k['q'],-1,k['p']))]))
def _unpem(text):return base64.b64decode(''.join(l for l in text.splitlines() if l and not l.startswith('-----')))
def _read(b,i=0):
 tag=b[i];n=b[i+1];at=i+2
 if n&0x80:c=n&0x7f;n=int.from_bytes(b[at:at+c],'big');at+=c
 return tag,at,at+n
def _children(b):
 tag,i,end=_read(b);out=[]
 while i<end:
  _,a,z=_read(b,i);out.append(b[i:z]);i=z
 return out
def read_key(text):
 nums=[int.from_bytes(b[_read(b)[1]:],'big') for b in _children(_unpem(text))]
 return dict(n=nums[1],e=nums[2],d=nums[3],p=nums[4],q=nums[5])
def _cert(subject,issuer_der,key,sign_key,days,exts):
 now=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=1)
 spki=_seq(_seq(_oid('1.2.840.113549.1.1.1'),_tlv(5,b'')),_bits(_public(key)))
 tbs=_seq(_tlv(0xa0,_int(2)),_int(secrets.randbits(63)|1<<62),SHA256RSA,issuer_der,
  _seq(_time(now),_time(now+datetime.timedelta(days=days+1))),subject,spki,_tlv(0xa3,_seq(*exts)))
 return _pem('CERTIFICATE',_seq(tbs,SHA256RSA,_bits(_sign(sign_key,tbs))))
def _key_use(bits_value,unused):return _tlv(3,bytes([unused,bits_value]))
def make_ca(cn,days=3650):
 k=new_key();name=_name(cn)
 return _cert(name,name,k,k,days,[_ext('2.5.29.19',_seq(_tlv(1,b'\xff')),True),_ext('2.5.29.15',_key_use(0x06,1),True),_ext('2.5.29.14',_tlv(4,_keyid(k)))]),key_pem(k)
def make_leaf(ca_pem,ca_key_pem,host,ips,days=800):
 ca_key=read_key(ca_key_pem);issuer=_children(_children(_unpem(ca_pem))[0])[5];k=new_key()
 san=[_tlv(0x82,host.encode('ascii','ignore') or b'localhost')]+[_tlv(0x87,socket.inet_aton(i)) for i in ips]
 return _cert(_name(host),issuer,k,ca_key,days,[_ext('2.5.29.19',_seq()),_ext('2.5.29.15',_key_use(0xa0,5),True),
  _ext('2.5.29.37',_seq(_oid('1.3.6.1.5.5.7.3.1'))),_ext('2.5.29.17',_seq(*san)),_ext('2.5.29.14',_tlv(4,_keyid(k))),
  _ext('2.5.29.35',_seq(_tlv(0x80,_keyid(ca_key))))]),key_pem(k)
def self_signed(cn,days=3650):
 k=new_key();name=_name(cn)
 return _cert(name,name,k,k,days,[_ext('2.5.29.19',_seq()),_ext('2.5.29.14',_tlv(4,_keyid(k)))]),key_pem(k)
def write_private(path,text):
 Path(path).write_text(text,encoding='ascii')
 try:Path(path).chmod(0o600)
 except OSError:pass
