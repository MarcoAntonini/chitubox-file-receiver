#!/usr/bin/python
#
# Chitubox File Receiver
#
# author: Marco Antonini marcomail.anto@gmail.com
# author: Ray Ramirez rramirez@revnull.com
#

import os
import platform
import socket
import struct
import subprocess
import sys
import traceback


# The printer name that we return to Chitubox
PRINTERNAME = "Mars Pro"

# The directory where we will store our transferred files
FILEPATH = "/mnt/usb_share/"

# Only accept only these file extentions. If Chitubox transfers a file that is
# not in this list, it will rejected and Chitubox will return an error.
FILES_ACCEPT = [".ctb", ".gcode"]

# Enable debug messages to the console
debug = True

# Network port where we will listen for Chitubox M99999 broadcasts
port = 3000

# Other globals
count = 0
fp = None
fileTransferStarted = False
fullFilePath = None
localIp = None

# Setup listener
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.bind(("", port))


def prnt(string):
    """
    Save some line space with a typo function for "print" :)
    """
    sys.stdout.write(string)


def get_localIp():
    """
    Determine local IP address for use with M99999
    """
    global localIp
    if platform.system() == "Darwin":
        localIp = socket.gethostbyname(socket.gethostname())
    else:
        p = subprocess.Popen(["hostname -I | cut -d' ' -f1"],
                             stdout=subprocess.PIPE, shell=True)
        localIp = p.communicate()[0]
    if debug:
        prnt("Info: Local IP = {0}\n".format(localIp))


def process_m28(message):
    """
    M28 is used to open and create streaming files
    """
    global fileTransferStarted, fullFilePath, FILEPATH, fp
    fileName = str(message).replace("M28 ", "")
    fullFilePath = "{0}{1}.temp".format(FILEPATH, fileName)
    if fp is not None:
        if not fp.closed:
            fp.close()

    accepted = False
    for i in range(0, len(FILES_ACCEPT)):
        if FILES_ACCEPT[i] in fileName:
            accepted = True
            break
        if FILES_ACCEPT[i].upper() in fileName:
            accepted = True
            break

    if not accepted:
        s.sendto("Error:write data \n", address)
        prnt("Error: Invalid file extention for {0}\n".format(fileName))
    else:
        try:
            fp = open(fullFilePath, "wb+")
            fileTransferStarted = True
            resp = "ok \r\n"
        except OSError:
            prnt("Error: Could not open {0}\n".format(fullFilePath))
            fileTransferStarted = False
            resp = "Error:write data \n"
    s.sendto(resp, address)
    if "ok" in resp:
        prnt("\nInfo: Created file {0}\n".format(fullFilePath))
    if debug:
        prnt("Recv: {0}\nSend: {1}\n".format(str(message), resp))


def process_m29(message):
    """
    M29 is used to close out a streaming file write and rename the local file
    """
    global fileTransferStarted, fp, fullFilePath
    resp = "ok \n"
    s.sendto(resp, address)
    fp.close()
    fileTransferStarted = False
    prnt("Info: {0} streaming writes complete\n".format(fullFilePath))
    os.rename(fullFilePath, fullFilePath.replace(".temp", ""))
    prnt("Info: {0} renamed to {1}\n".format(
        fullFilePath, fullFilePath.replace(".temp", "")))
    if debug:
        prnt("Recv: {0}\nSend: {1}\n".format(str(message), resp))


def process_m30(message):
    """
    M30 is used to process file deletion requests
    """
    global fileTransferStarted, fp, fullFilePath
    fileName = str(message).replace("M30 ", "")
    fp.close()
    fileTransferStarted = False
    try:
        os.remove(fullFilePath)
        resp = "File deleted :{0} \n".format(fileName)
    except OSError:
        resp = "Delete failed :{0} \n".format(fileName)
    s.sendto(resp, address)
    s.sendto("ok \n", address)
    if debug:
        prnt("\n\nInfo: Received a request to delete {0}\n".format(fileName))
        prnt("Recv: {0}\nSend: {1}".format(str(message), resp))


def process_m4001(message):
    """
    M4001 requests character encoding to use for streaming file transfer
    """
    resp = "ok. X:0.0 Y:0.0 Z:0.00125 U:'UTF-8' \n"
    s.sendto(resp, address)
    if debug:
        prnt("Info: Received request for charactor encoding\n")
        prnt("Recv: {0}\nSend: {1}".format(str(message), resp))


def process_m4012(message):
    """
    M4012 requests the number of blocks sent and received
    """
    resp = "ok {0}/{1} \n".format(str(fp.tell()), str(fp.tell()))
    s.sendto(resp, address)
    if debug:
        prnt("\n\nInfo: Received block count validation request.\n")
        prnt("Recv: {0}\nSend: {1}\n".format(str(message), resp))


def process_m6030(message):
    """
    M6030 requests the "printer" to start printing the uploaded file
    We do not have access to those controls so we respond with 'ok"
    and do nothing.
    """
    fileName = str(message).replace("M6030 ", "")
    resp = "ok \n"
    s.sendto(resp, address)
    if debug:
        prnt("Info: Recvied request to print {0}\n".format(fileName))
        prnt("Info: Sent 'ok', but not a printer, so do nothing.\n")
        prnt("Recv: {0}\nSend: {1}\n".format(str(message), resp))


def process_m99999(message):
    """
    M99999 is used to process Chitubox brocast requests
    """
    resp = "ok. NAME:{0} IP:{1} \n".format(PRINTERNAME, localIp)
    s.sendto(resp, address)
    if debug:
        prnt("Info: Received broadcast request from {0}\n".format(address[0]))
        prnt("Recv: {0}\nSend: {1}".format(str(message), resp))


def process_write_stream(message):
    """
    Used to process and validate incoming write stream data
    """
    global fp, count, fullFilePath
    # Current File position
    filePos = fp.tell()
    # Last 6 bytes contain the test data
    test_data = message[messageLen - 6:]
    # Valid Data without the 6 bytes of the test
    validData = message[: messageLen - 6]
    # File position Bit converter into 4 bytes
    index = struct.pack("i", filePos)
    test = True

    # Check data position is equal to the current file position
    if not test_data[:4] == index:
        test = False

    # Test XOR Calculation
    num8 = 0
    # perform test
    for i in range(0, messageLen - 6):
        num8 = num8 ^ ord(message[i])
    for i in range(0, 4):
        num8 = num8 ^ ord(index[i])

    # Check if XOR calculation is equal to test data
    if not num8 == ord(test_data[4]):
        test = False

    # The test passed, lets write valid data to the file
    if test:
        try:
            fp.write(validData)
            s.sendto("ok \n", address)
            count += 1
            prnt("\rInfo: Writing data chunk {0} to {1}".format(
                count, fullFilePath))
            sys.stdout.flush()
        except OSError:
            s.sendto("Error:write data \n", address)
            prnt("Error: Couldn't write data into {0}\n".format(fullFilePath))
            fp.close()
            os.remove(fullFilePath)
        tryResend = 0

    # The test failed, lets request Chitubox to Resend
    else:
        if tryResend < 3:
            s.sendto("resend {0} \n".format(str(filePos)), address)
            tryResend += 1
            prnt("Info: Resend request = index {0}\n".format(str(filePos)))
        else:
            prnt("Error: Resend failed\n")
            s.sendto("Error:write data \n", address)
            fp.close()
            os.remove(fullFilePath)


def process_unknown(message):
    """
    Inform when Chitubox is sending unexpected gcodes
    """
    prnt("\nError: Encountered an unexpected gcode command = {0}\n".format(
        str(message)))


# Lets get to work...
prnt("Info: Chitubox file receiver is now listening on the port {0}\n".format(
    str(port))
)

get_localIp()

while True:
    try:
        isData = False
        tryResend = 0
        message, address = s.recvfrom(8192)
        messageLen = len(message)

        # Check the message to see if it's a data chunk
        if messageLen > 6 and message[messageLen - 1] == "\x83":
            isData = True

        if not fileTransferStarted and not isData:
            if "M99999" in str(message):
                process_m99999(message)
            elif "M28" in str(message):
                process_m28(message)
            elif "M30" in str(message):
                process_m30(message)
            elif "M4001" in str(message):
                process_m4001(message)
            elif "M6030" in str(message):
                process_m6030(message)
            else:
                process_unknown(message)
        elif "M29" in str(message) and not isData:
            process_m29(message)
        elif "M30" in str(message) and not isData:
            process_m30(message)
        elif "M4012" in str(message) and not isData:
            process_m4012(message)
        elif fileTransferStarted and isData:
            process_write_stream(message)
        elif not isData:
            process_unknown(message)

    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        traceback.print_exc()
