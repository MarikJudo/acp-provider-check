# minimal keccak-256
def keccak256(msg:bytes)->bytes:
    RC=[0x0000000000000001,0x0000000000008082,0x800000000000808A,0x8000000080008000,
        0x000000000000808B,0x0000000080000001,0x8000000080008081,0x8000000000008009,
        0x000000000000008A,0x0000000000000088,0x0000000080008009,0x000000008000000A,
        0x000000008000808B,0x800000000000008B,0x8000000000008089,0x8000000000008003,
        0x8000000000008002,0x8000000000000080,0x000000000000800A,0x800000008000000A,
        0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008]
    R=[[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]
    def rol(x,n): return ((x<<n)|(x>>(64-n)))&0xFFFFFFFFFFFFFFFF
    rate=136
    st=[[0]*5 for _ in range(5)]
    # pad
    msg=bytearray(msg); msg.append(0x01)
    while len(msg)%rate!=0: msg.append(0)
    msg[-1]^=0x80
    for off in range(0,len(msg),rate):
        block=msg[off:off+rate]
        for i in range(rate//8):
            x=i%5; y=i//5
            st[x][y]^=int.from_bytes(block[i*8:i*8+8],'little')
        for rnd in range(24):
            C=[st[x][0]^st[x][1]^st[x][2]^st[x][3]^st[x][4] for x in range(5)]
            D=[C[(x-1)%5]^rol(C[(x+1)%5],1) for x in range(5)]
            for x in range(5):
                for y in range(5): st[x][y]^=D[x]
            B=[[0]*5 for _ in range(5)]
            for x in range(5):
                for y in range(5): B[y][(2*x+3*y)%5]=rol(st[x][y],R[x][y])
            for x in range(5):
                for y in range(5): st[x][y]=B[x][y]^((~B[(x+1)%5][y])&B[(x+2)%5][y])
            st[0][0]^=RC[rnd]
    out=bytearray()
    for i in range(4):
        x=i%5; y=i//5
        out+=st[x][y].to_bytes(8,'little')
    return bytes(out)
if __name__=="__main__":
    assert keccak256(b"").hex()=="c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", keccak256(b"").hex()
    print("keccak self-test OK")
