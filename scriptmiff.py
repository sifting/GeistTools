#!/usr/bin/env python3
from struct import unpack, pack
import argparse
import csv

#There has got to be a better way to do this
def safestring (string):
    s = ''
    for c in string:
        if c >= 32 and c <= 127: s += chr (c)
        else: break
    return s

def miffunpack (file):
    lines = []

    def extract (data):
        unk0, elength = unpack (f'<II', data[:8]); data = data[8:]
        etext = data[:elength].decode ('shift-jis').replace ('\0', ''); data = data[elength:]
        jlength = unpack (f'<I', data[:4])[0]; data = data[4:]
        jtext = data[:jlength].decode ('shift-jis').replace ('\0', ''); data = data[jlength:]
        llength = unpack (f'<I', data[:4])[0]; data = data[4:]
        link = data[:llength].decode ('shift-jis').replace ('\0', '');
        return [link, unk0, jtext]

    with open (file, 'rb') as f:
        magick = f.read (4).decode ('latin')
        if 'MIFF' != magick:
            raise Exception (f'{file} is NOT a MIFF!')
    
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

            lines.append ([mname] + extract (contents))

            read += 8 + rlength
    
    #Now dump the lines into a csv for Yakumo
    with open (f'script.csv', 'w', newline='') as f:
        writer = csv.writer (f, delimiter=';', quotechar='\"', escapechar='\\', quoting=csv.QUOTE_MINIMAL)
        for ln in lines:
            writer.writerow (ln)

def miffpack (file):
    def padstring (string):
        if len (string) == 0:
            return bytes ()
        
        s = bytes (string.encode ('shift-jis'))
        aligned = (len (s)+2)&~1
        count = aligned - len (s)
        for i in range (count):
            s += '\0'.encode ('latin')
        return s

    data = bytearray ()
    with open (file, newline='') as f:
        reader = csv.reader (f, delimiter=';', quotechar='\"', escapechar='\\', quoting=csv.QUOTE_MINIMAL)
        for row in reader:
            print (row)
            
            er0 = padstring (row[0])
            er1 = padstring (row[1])
            er3 = padstring (row[3])

            record = bytearray ()
            record += pack ('<ff', 1.0, 1.0)
            record += pack ('<I', len (er0))
            record += er0
            record += pack ('<I', 0)
            record += pack ('<II', int (row[2]), 0)
            record += pack ('<I', len (er3))
            record += er3
            record += pack ('<I', len (er1))
            record += er1

            header = bytearray ()
            header += bytes ('GScr'.encode ('latin'))
            header += pack ('>I', len (record))
            
            data += header + record 
            
    
    miff = bytearray ()
    miff += bytes ('MIFF'.encode ('latin'))
    miff += pack ('>I', 12 + len (data))
    miff += bytes ('Litl'.encode ('latin'))
    miff += data
    with open ('SCRIPT.MIFF', 'wb') as f:
        f.write (miff)
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser (description='(Un)packs Geist Force script MIFFs')
    parser.add_argument('--pack', help='Builds a MIFF from a CSV file')
    parser.add_argument('--unpack', help='Extracts MIFF into a CSV file')
    args = parser.parse_args ()
    
    if args.unpack:
        miffunpack (args.unpack)

    if args.pack:
        miffpack (args.pack)
