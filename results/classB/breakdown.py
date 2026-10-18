import json,sys,numpy as np,os
def hm(s):
    h,m,x=map(int,s.split(':'));return h*3600+m*60+x
def run(d,f):
    os.chdir(d); m=json.load(open('model.json')); nz=np.load('model.npz')
    chg=nz['chg']; names=m['names']; ix={n:i for i,n in enumerate(names)}
    r=json.load(open(f)); it=r['itin']; tot=r['stats']['total_s']
    ride=rideb=walk=trans=wait=0; seen=set(); nb=0; back=[]
    prev=None
    t0=hm(it[0]['t0'])
    for k,l in enumerate(it):
        a,b=hm(l['t0']),hm(l['t1'])
        if k>0:
            gap=a-hm(it[k-1]['t1'])
            p=it[k-1]
            if l['kind']=='ride' and p['kind']=='ride' and p['to']==l['from']:
                c=min(gap,int(chg[ix[l['from']]]))
                # same train continuing? gap 0 ->
                trans+=c; wait+=gap-c
            else: wait+=gap
        if l['kind']=='ride':
            ride+=b-a
            if l['new']==0: rideb+=b-a; nb+=1; back.append((l['route'],l['from'],l['to'],(b-a)//60))
        else: walk+=b-a
    h=lambda s:'%.2f h'%(s/3600)
    print(f,'total',h(tot),'ride',h(ride),'(of which no-new-station rides',nb,h(rideb),')walk',h(walk),'transfer',h(trans),'wait',h(wait),'| sum',h(ride+walk+trans+wait), 'rides',sum(1 for l in it if l['kind']=='ride'),'walks',sum(1 for l in it if l['kind']!='ride'))
    return back
if __name__=='__main__':
    for d,f in (('A','r3.json'),('A','r1.json'),('B','r2.json')):
        b=run('/tmp/claude-0/g/cb/'+d,f)
        if f=='r1.json': print(b[:20])
