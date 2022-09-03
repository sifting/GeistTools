#!/usr/bin/env python3
from struct import unpack, pack
import argparse
import png
import csv
import io
import os

def verify (cond, msg):
    if not cond:
        raise Exception (msg)

def pvr_decode (data, total, px, fmt, width, height):
    #Some PVR constants
    CODEBOOK_SIZE = 2048
    MAX_WIDTH = 0x80000
    MAX_HEIGHT = 0x80000
    
    #Image must be one of these
    ARGB1555 = 0x0
    RGB565   = 0x1
    ARGB4444 = 0x2
    YUV422   = 0x3
    BUMP     = 0x4
    PAL_4BPP = 0x5
    PAL_8BPP = 0x6
    
    #And one of these
    SQUARE_TWIDDLED            = 0x1
    SQUARE_TWIDDLED_MIPMAP     = 0x2
    VQ                         = 0x3
    VQ_MIPMAP                  = 0x4
    CLUT_TWIDDLED_8BIT         = 0x5
    CLUT_TWIDDLED_4BIT         = 0x6
    DIRECT_TWIDDLED_8BIT       = 0x7
    DIRECT_TWIDDLED_4BIT       = 0x8
    RECTANGLE                  = 0x9
    RECTANGULAR_STRIDE         = 0xB
    RECTANGULAR_TWIDDLED	   = 0xD
    SMALL_VQ                   = 0x10
    SMALL_VQ_MIPMAP            = 0x11
    SQUARE_TWIDDLED_MIPMAP_ALT = 0x12
    
    #For printing the above
    TYPES = [
        'ARGB1555',
        'RGB565',
        'ARGB4444',
        'YUV422',
        'BUMP',
        '4BPP',
        '8BPP'
    ]
    FMTS = [
        'UNK0',
        'SQUARE TWIDDLED',
        'SQUARE TWIDDLED MIPMAP',
        'VQ',
        'VQ MIPMAP',
        'CLUT TWIDDLED 8BIT',
        'CLUT TWIDDLED 4BIT',
        'DIRECT TWIDDLED 8BIT',
        'DIRECT TWIDDLED 4BIT',
        'RECTANGLE',
        'UNK1',
        'RECTANGULAR STRIDE',
        'UNK2',
        'RECTANGULAR TWIDDLED',
        'UNK3',
        'UNK4',
        'SMALL VQ',
        'SMALL VQ MIPMAP',
        'SQUARE TWIDDLED MIPMAP ALT'
    ]

    #Print info and verify
    print (f'    Type: {TYPES[px]} {FMTS[fmt]}, Size: {width}x{height}')
    verify (width <= MAX_WIDTH, f'width is {width}; must be < {MAX_WIDTH}')
    verify (height <= MAX_HEIGHT, f'height is {height}; must be < {MAX_HEIGHT}')
    
    #This is my favourite black magic spell!
    #Interleaves x and y to produce a morton code
    #This trivialises decoding PVR images
    def morton (x, y):
        x = (x|(x<<8))&0x00ff00ff
        y = (y|(y<<8))&0x00ff00ff
        x = (x|(x<<4))&0x0f0f0f0f
        y = (y|(y<<4))&0x0f0f0f0f
        x = (x|(x<<2))&0x33333333
        y = (y|(y<<2))&0x33333333
        x = (x|(x<<1))&0x55555555	
        y = (y|(y<<1))&0x55555555
        return x|(y<<1)
    
    #Colour decoders...
    def unpack1555 (colour):
        a = int (255*((colour>>15)&31))
        r = int (255*((colour>>10)&31)/31.0)
        g = int (255*((colour>> 5)&31)/31.0)
        b = int (255*((colour    )&31)/31.0)
        return [r, g, b, a]
        
    def unpack4444 (colour):
        a = int (255*((colour>>12)&15)/15.0)
        r = int (255*((colour>> 8)&15)/15.0)
        g = int (255*((colour>> 4)&15)/15.0)
        b = int (255*((colour    )&15)/15.0)
        return [r, g, b, a]
    
    def unpack565 (colour):
        r = int (255*((colour>>11)&31)/31.0)
        g = int (255*((colour>> 5)&63)/63.0)
        b = int (255*((colour    )&31)/31.0)
        return [r, g, b]
    
    #Format decoders...
    #GOTCHA: PVR stores mipmaps from smallest to largest!
    def vq_decode (raw, decoder):
        pix = []
        
        #Extract the codebook
        tmp = raw
        book = unpack (f'<1024H', tmp[:CODEBOOK_SIZE])
        
        #Skip to the largest mipmap
        #NB: This also avoids another gotcha:
        #Between the codebook and the mipmap data is a padding byte
        #Since we only want the largest though, it doesn't affect us
        size = len (raw)
        base = width*height//4
        lut = raw[size - base : size]
        
        #The codebook is a 2x2 block of 16 bit pixels
        #This effectively halves the image dimensions
        #Each index of the data refers to a codebook entry
        for i in range (height//2):
            row0 = []
            row1 = []
            for j in range (width//2):
                entry = 4*lut[morton (i, j)]
                row0.extend (decoder (book[entry + 0]))
                row1.extend (decoder (book[entry + 1]))
                row0.extend (decoder (book[entry + 2]))
                row1.extend (decoder (book[entry + 3]))
            pix.insert (0, row0)
            pix.insert (0, row1)
        return pix
    
    def morton_decode (raw, decoder):
        pix = []
        
        #Skip to largest mipmap
        size = len (raw)
        base = width*height*2
        mip = raw[size - base : size]
        
        data = unpack (f'<{width*height}H', mip)
        for i in range (height):
            row = []
            for j in range (width):
                if j <= i: colour = data[morton (i, j)]
                else: colour = data[morton (j, i)]
                row.extend (decoder (colour))
            pix.insert (0, row)
        return pix
    
    def linear_decode (raw, decoder):
        pix = []
        
        #Skip to largest mipmap
        size = len (raw)
        base = width*height*2
        mip = raw[size - base : size]
        
        data = unpack (f'<{width*height}H', mip)
        for i in range (height):
            row = []
            for j in range (width):
                row.extend (decoder (data[i*width + j]))
            pix.insert (0, row)
        return pix

    #From observation:
    #All textures 16 bit
    #All textures are either VQ'd or morton coded (twiddled)
    #So let's just save time and only implement those
    if ARGB1555 == px:
        if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
            return morton_decode (data, unpack1555), 'RGBA'
        elif VQ == fmt or VQ_MIPMAP == fmt:
            return vq_decode (data, unpack1555), 'RGBA'
        else:
            return linear_decode (data, unpack1555), 'RGBA'
    elif ARGB4444 == px:
        if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
            return morton_decode (data, unpack4444), 'RGBA'
        elif VQ == fmt or VQ_MIPMAP == fmt:
            return vq_decode (data, unpack4444), 'RGBA'
        else:
            return linear_decode (data, unpack4444), 'RGBA'
    elif RGB565 == px:
        if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
            return morton_decode (data, unpack565), 'RGB'
        elif VQ == fmt or VQ_MIPMAP == fmt:
            return vq_decode (data, unpack565), 'RGB'
        else:
            return linear_decode (data, unpack565), 'RGB'
    
    #Oh, well...
    return 'Unsupported encoding', 'ERROR'

def decode_bmp (data, endian):
    f0, unk0, unk1, f1, unk2, width, height, unk3 = unpack (f'<4B4I', data[:20])
    print (f'ts {f0}, {f1}, {width}x{height}')
    if 0xe0 == f1:
        fmt = 3 #vq no mip
        if f0 == 3: px = 2
        else: px = 1
    elif 0xa0 == f1:
        fmt = 1
        px = 2
    elif 0xc0 == f1:
        fmt = 3
        px = 1
    elif 0xd0 == f1:
        fmt = 4 #vq with mipmaps
        px = 1
    elif 0xf0 == f1:
        fmt = 4
        if f0 == 3: px = 2
        else: px = 1
    elif 0x80 == f1:
        fmt = 1
        if f0 == 4: px = 0
        else: px = 1
    elif 0x20 == f1:
        fmt = 9 #novq, rectangle
        px = 2
    elif 0x00 == f1:
        fmt = 9
        px = 1
    else:
        fmt = 1 #novq, twiddled
        px = 1
    pixels, status = pvr_decode (data[20:], len (data) - 20, px, fmt, width, height)
    return pixels, status

class dump_image:
    path = ''

    def process ():
        pass
    
    def __init__ (self, rtype, rlength, mname, contents):
        import pathlib
        dn = os.path.join ('root', *pathlib.PurePath (dump_image.path).parts[1:])
        os.makedirs (dn, exist_ok = True)
        if 'MBmp' == rtype:
            ret, mode = decode_bmp (contents, '<')
            png.from_array (ret, mode).save (os.path.join (dn, os.path.basename (mname) + '.png'))

class dump_raw:
    def process ():
        pass
    
    def __init__ (rtype, rlength, mname, contents):
        with open (mname, 'wb') as of:
            of.write (contents)

class gltf:
    def __init__ (self):
        self.bin = bytearray ()
        self.views = []
        self.accessors = []


class dump_asset:
    actions = []
    materials = []
    groups = []
    points = []

    def parse_actions (data):
        count = unpack ('<I', data.read (4))[0]
        for i in range (count):
            unk0, frame, unk2, length = unpack ('<IfII', data.read (16))
            tag = data.read (length).decode ('shift-jis').replace ('\0', '')
            dump_asset.actions.append ([tag, frame])

    def parse_model (data):
        unk0, ngroups = unpack ('<II', data.read (8))
        for i in range (ngroups):
            unk1, unk2, mlen = unpack ('<III', data.read (12))
            
            material = data.read (mlen).decode ('shift-jis').replace ('\0', '')
            dump_asset.materials.append (material)

            verts = []
            unk3, nverts = unpack ('<II', data.read (8))
            for j in range (nverts):
                point, flags, u, v, argb, a, r, g, b = unpack ('<HHffI4f', data.read (32))
                verts.append ([point, flags, u, v, argb, a, r, g, b])
            
            punk = []
            npunk = unpack ('<I', data.read (4))[0]
            for j in range (npunk):
                x, y, z = unpack ('<3f', data.read (12))
                punk.append ([x, y, x])

            norms = []
            nnorms = unpack ('<I', data.read (4))[0]
            for j in range (nnorms):
                x, y, z = unpack ('<3f', data.read (12))
                norms.append ([x, y, z])

            unk4, unk5, unk6 = unpack ('<3I', data.read (12))

            dump_asset.groups.append ([material, verts, punk, norms, unk3])

        npoints = unpack ('<I', data.read (4))[0]
        for j in range (npoints):
            x, y, z = unpack ('<3f', data.read (12))
            dump_asset.points.append ([x, y, z])
        
        unk7, xmx, ymx, zmx, xmn, ymn, zmn = unpack ('<I3f3f', data.read (28))
        
    def process ():
        for k in dump_asset.actions:
            print (k)
        
        total = 0
        for mdl in dump_asset.groups:
            print (mdl[0])
            print (len (mdl[1]))
            tris = 0
            faces = 0
            mi = 99999
            mx =-99999
            for v in mdl[1]:
                point = v[0]&0x7fff
                eos = v[0]&0x8000
                print (f'{point},{v[1]}({eos}) : {v[2]:.2f},{v[3]:.2f} : {v[4]:08X} : {v[5]:.2f},{v[6]:.2f},{v[7]:.2f},{v[8]:.2f}')
                tris += 1
                
                if point < mi: mi = point
                if mx < point: mx = point 
                
                if eos:
                    print (f'point min: {mi}')
                    print (f'point max: {mx}')
                    if 0 == mi:
                        total += mx + 1
                    mi = 99999
                    mx =-99999

                    print (f'tris: {tris - 2}')
                    faces += tris - 2
                    tris = 0

            print (f'faces: {faces}')
            print (f'unk3: {mdl[4]}')
            

            print ('punk')
            index = 0
            for p in mdl[2]:
                print (f'{index} {p[0]:.2f} {p[1]:.2f} {p[2]:.2f}')
                index += 1
            print ('normals')
            index = 0
            for p in mdl[3]:
                print (f'{index} {p[0]:.2f} {p[1]:.2f} {p[2]:.2f}')      
                index += 1
        print ('points')
        index = 0
        for v in dump_asset.points:
            print (f'{index} {v[0]:.2f}, {v[1]:.2f}, {v[2]:.2f}')
            index += 1
        print (f'total: {total}')
    
        
    def __init__ (self, rtype, rlength, mname, contents):
        parsers = {
            'MAct' : dump_asset.parse_actions,
            'MMdl' : dump_asset.parse_model
        }
        data = io.BytesIO (contents)
        for k, v in parsers.items ():
            if rtype != k:
                continue    
            v (data)
            return
        print (f'{rtype}: ignoring...')
        return




def safestring (string):
    s = ''
    for c in string:
        if c >= 32 and c <= 127: s += chr (c)
        else: break
    return s

def miffparse (file, functor):
    functor.path = file

    with open (file, 'rb') as f:
        magick = f.read (4).decode ('latin')
        if 'MIFF' != magick:
            raise Exception (f'{file} is not a MIFF!')
    
        size = unpack ('>I', f.read (4))[0]
        endian = f.read (4).decode ('latin')

        if 'Litl' == endian: ls = '<'
        else: ls = '>'

        print (f'MIFF: {file}')
        print (f'SIZE: {size}')
        print (f'ENDIANNESS: {endian}')

        read = f.tell ()
        while read < size:
            #Record info
            rtype = f.read (4).decode ('latin')
            rlength = unpack ('>I', f.read (4))[0]

            #Meta data and file contents
            munk0, munk1, mlen = unpack (f'{ls}ffI', f.read (12))
            mname = safestring (f.read (mlen))
            mmfln = unpack (f'{ls}I', f.read (4))[0]
            mmfl = safestring (f.read (mmfln))

            contents = f.read (rlength - mlen - mmfln - 16)

            print (f'Processing {rtype}:{rlength}:{mname}...')
            functor (rtype, rlength, mname, contents)

            read += 8 + rlength
    #Process the inputs
    functor.process ()

if __name__ == '__main__':
    parser = argparse.ArgumentParser (description='Miff manipulation tool')
    parser.add_argument('--asset', help='Writes an asset to GLTF')
    parser.add_argument('--image', help='Writes images to disk')
    args = parser.parse_args ()
    
    if args.asset:
        miffparse (args.asset, dump_asset)

    if args.image:
        miffparse (args.image, dump_image)

