import sys

def main (file, chunksize):
    #Read the whole file
    with open (file, 'rb') as f:
        data = f.read ()
    #Open mono streams
    with open ('l.adpcm', 'wb') as l:
        with open ('r.adpcm', 'wb') as r:
            for i in range (0, len (data), 2*chunksize):
                l.write (data[i:i + chunksize])
                r.write (data[i + chunksize:i + 2*chunksize])

main (sys.argv[1], int(sys.argv[2]))