#!/usr/bin/python
#
# Chitubox Files Receiver
#
# author: Marco Antonini marcomail.anto@gmail.com
#

import socket, traceback
import struct
import os, subprocess
import platform
import sys


PRINTERNAME = 'Mars Pro'
# Directory containing the print files
FILEPATH = '/mnt/usb_share/'
# Accept only these files
# if transferred a file that is not in this list, it will not be accepted and Chitubox will return an error
FILES_ACCEPT = [ '.ctb' , '.gcode' ]

debug = True
port = 3000

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.bind(('', port))

fp = None
filename = ''
fileTransferStarted = False
count=0
print("Info: Chitubox file receiver listening on the port {0}".format(str(port)))

while True:
    try:

        tryResend = 0
        message, address = s.recvfrom(8192)
        messageLen = len(message)

        if not fileTransferStarted and not message[messageLen-1] == '\x83':
            # Device Name and Ip request
            if 'M99999' in str(message):
                localip = ''
                if platform.system() == "Darwin":
                    localip = socket.gethostbyname(socket.gethostname())
                else:
                    p = subprocess.Popen(
                        ["hostname -I | cut -d' ' -f1"],
                        stdout=subprocess.PIPE,
                        shell=True,
                    )
                    localip = p.communicate()[0]
                if debug:
                    print("Info: Local IP = {0}".format(localip))

                resp = "ok. NAME:{0} IP:{1} \n".format(PRINTERNAME, localip)
                s.sendto(resp, address)
                if debug:
                    print("\nRecv: {0}\nSend: {1}".format(str(message), resp))

            # File Name
            elif 'M28' in str(message):
                filename= "{0}{1}.temp".format(FILEPATH, str(message).replace('M28 ',""))
                
                if fp is not None:
                    if not fp.closed:
                        fp.close()
    
                accepted = False
                for i in range(0,len(FILES_ACCEPT)):
                    if FILES_ACCEPT[i] in filename:
                        accepted = True
                        break
                    if FILES_ACCEPT[i].upper() in filename:
                        accepted = True
                        break

                if not accepted:
                    s.sendto("Error:write data \n", address)
                else:
                    try:
                        fp = open(filename,'wb+')
                        fileTransferStarted = True
                        resp = "ok \r\n"
                    except:
                        print("Error: Could not open ".format(filename))
                        fileTransferStarted = False
                        resp = "Error:write data \n"

                s.sendto(resp, address)
                if "ok" in resp:
                    print("Info: File {0} opened".format(filename))
                if debug:
                    print("\nRecv: {0}\nSend: {1}".format(str(message), resp))

            # Encoding Request
            elif 'M4001' in str(message):
                resp = "ok. X:0.0 Y:0.0 Z:0.00125 U:'UTF-8' \n"
                s.sendto(resp, address)
                if debug:
                    print("\nRecv: {0}\nSend: {1}".format(str(message), resp))

            # Start Print Request
            elif "M6030" in str(message):
                resp = "ok \n"
                s.sendto(resp, address)
                if debug:
                    print("\nRecv: {0}\nSend: {1}".format(str(message), resp))
                    print("Info: Sent 'ok' but we do nothing.")

            else:
                print("Error: Unknown command = {0}".format(str(message)))


        # End of File Request
        elif 'M29' in str(message) and not message[messageLen-1] == '\x83':
            resp = "ok \n"
            s.sendto(resp, address)
            fp.close()
            fileTransferStarted = False
            os.rename(filename,filename.replace('.temp',''))
            if debug:
                print(
                    "Info: {0} renamed to {1}".format(filename, filename.replace('.temp',''))
                )
                print("\nRecv: {0}\nSend: {1}".format(str(message), resp))
            print("Info: {0} write complete".format(filename.replace('.temp','')))

        elif 'M4012 I' in str(message) and not message[messageLen-1] == '\x83':
            resp = "ok {0}/{1} \n".format(str(fp.tell()), str(fp.tell()))
            s.sendto(resp, address)
            if debug:
                print("\nRecv: {0}\nSend: {1}".format(str(message), resp))

        # Delete File Request
        elif 'M30' in str(message) and not message[messageLen-1] == '\x83':
            filename = str(message).replace('M30 ',"")
            fp.close()
            fileTransferStarted = False
            try:
                os.remove(FILEPATH+filename)
                resp = "File deleted :{0} \n".format(filename)
                s.sendto(resp, address)
            except:
                resp = "Delete failed :{0} \n".format(filename)

            s.sendto(resp, address)


            if debug:
                print("\nRecv: {0}\nSend: {1}".format(str(message), resp))

        # Data File
        elif messageLen > 6 and message[messageLen-1] == '\x83' and fileTransferStarted:

            # Current File position
            filePos = fp.tell()
            # Last 6 bytes contain the test data
            test_data = message[messageLen-6:]
            # Valid Data without the 6 bytes of the test
            validData = message[:messageLen-6]
            # File position Bit converter into 4 bytes
            index=struct.pack('i',filePos)
            test = True

            # Check data position is equal to the current file position
            if not test_data[:4] == index:
                test = False

            # Test XOR Calculation
            num8=0
            # perform test
            for i in range(0,messageLen-6):
                num8 = num8 ^ ord(message[i])
            for i in range(0,4):
                num8 = num8 ^ ord(index[i])

            # Check if XOR calculation is equal to test data
            if not num8 == ord(test_data[4]):
                test = False

            # Test is ok, Write valid data to file
            if test:
                try:
                    fp.write(validData)
                    s.sendto("ok \n", address)
                    if debug:
                        sys.stdout.write("\rInfo: Data chunk {0} written to {1}".format(count, filename))
                        sys.stdout.flush()
                except:
                    s.sendto("Error:write data \n", address)
                    print("Error: Could not write data into {0}".format(filename))
                    fp.close()
                    os.remove(filename)

                tryResend=0

            # Test is not ok, try Resend
            else:
                if tryResend < 3:
                    s.sendto("resend {0} \n".format(str(filePos)), address)
                    tryResend += 1
                    print("Info: Resend request = index {0}".format(str(filePos)))
                else:
                    print("Error: Resend failed")
                    s.sendto("Error:write data \n", address)
                    fp.close()
                    os.remove(filename)

        elif not message[messageLen-1] == '\x83':
            print("Warn: Unknown command = {0}".format(str(message)))


    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        traceback.print_exc()
