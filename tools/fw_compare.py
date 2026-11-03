import collections, pathlib, re, sys, itertools
R=pathlib.Path('/home/magicaltux/projects/ledger_nano_re/firmware')
HX=re.compile(r'"([0-9A-Fa-f]+)"')
def L(n): return [bytes.fromhex(h) for h in HX.findall((R/f'btchipfirmware-{n}.js').read_text())]
def shape(a): return [(x[:2].hex().upper(),x[2],x[3],x[4]) for x in a]
vers=['1100','1101','1102','1103','1104']
print("== loader structure 1104 (runs)")
a=L('loader-1104')
for k,g in itertools.groupby(a,key=lambda x:(x[:4].hex().upper(),x[4])):
    g=list(g); print(k,len(g), g[0][5:13].hex() if k[1]<=8 and k[1]>0 else '')
print("== non-E006 apdus 1104"); 
for i,x in enumerate(a):
    if x[1]!=6: print(i,x.hex().upper())
print("== shape equal across versions?")
for g in ['loader','loader-from-loader','reloader','reloader-from-loader']:
    s={v:shape(L(f'{g}-{v}')) for v in vers}
    print(g, all(s[v]==s['1104'] for v in vers))
print("== apdu-level identical between adjacent versions")
for g in ['loader','loader-from-loader','reloader','reloader-from-loader','init']:
    for p,q in zip(vers,vers[1:]):
        A,B=L(f'{g}-{p}'),L(f'{g}-{q}')
        same=sum(x==y for x,y in zip(A,B)); 
        first=next((i for i,(x,y) in enumerate(zip(A,B)) if x!=y),None)
        print(f'{g} {p}->{q}: same {same}/{min(len(A),len(B))} first diff {first}')
print("== block-level common between 1103 and 1104 loaders, any offset")
A=b''.join(x[5:] for x in L('loader-1103')); B=b''.join(x[5:] for x in L('loader-1104'))
sa={A[i:i+8] for i in range(0,len(A)-7,8)}; sb=[B[i:i+8] for i in range(0,len(B)-7,8)]
print('common 8-byte aligned', sum(b in sa for b in sb),'/',len(sb), 'same offset', sum(A[i:i+8]==B[i:i+8] for i in range(0,len(A)-7,8)))
print("== repeated blocks in loader-from-loader")
for v in vers:
    a=L(f'loader-from-loader-{v}')
    c=collections.Counter(); pos=collections.defaultdict(list); off=0
    for i,x in enumerate(a):
        d=x[5:]
        for j in range(0,len(d)-7,8):
            c[d[j:j+8]]+=1; pos[d[j:j+8]].append((i,x[:2].hex().upper(),j))
        off+=len(d)
    print(v,[(k.hex(),n,pos[k]) for k,n in c.items() if n>1])
print("== from-loader 1104 structure")
a=L('loader-from-loader-1104')
for i,x in enumerate(a):
    print(i,x[:5].hex().upper(),x[5:13].hex() if x[4] else '')
print("== init")
for v in vers:
    for x in L(f'init-{v}'): print(v,x[:5].hex().upper(),x[5:].hex())
print("== E005/E008 cross-version")
for v in vers:
    a=L(f'loader-{v}'); print(v,[x.hex() for x in a if x[1]==5],[x.hex() for x in a if x[1]==8])
