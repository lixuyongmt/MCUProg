#coding: utf-8

class FileFormatError(IOError): pass

class Segment:
    """store a string with memory contents along with its startaddress"""
    def __init__(self, startaddress = 0, data=None):
        if data is None:
            self.data = ''
        else:
            self.data = data
        self.startaddress = startaddress

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "Segment(startaddress=0x%04x, data=%r)" % (self.startaddress, self.data)

class Memory:
    """represent memory contents. with functions to load files"""
    def __init__(self, filename=None):
        self.segments = []
        if filename:
            self.filename = filename
            self.loadFile(filename)

    def append(self, seg):
        self.segments.append(seg)

    def __getitem__(self, index):
        return self.segments[index]

    def __len__(self):
        return len(self.segments)

    def __repr__(self):
        return "Memory:\n%s" % ('\n'.join([repr(seg) for seg in self.segments]),)
    
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def loadIHex(self, file):
        """load data from a (opened) file in Intel-HEX format"""
        segmentdata = []
        extSegAddr = 0
        currentAddr = 0
        startAddr   = 0
        lines = file.readlines()
        for l in lines:
            if not l.strip(): continue  #skip empty lines
            if l[0] != ':': raise FileFormatError("line not valid intel hex data: '%s...'" % l[0:10])
            l = l.strip()               #fix CR-LF issues...
            length  = int(l[1:3],16)
            address = int(l[3:7],16) + extSegAddr
            type    = int(l[7:9],16)
            check   = int(l[-2:],16)
            if type == 0x00:
                if currentAddr != address:
                    if segmentdata:
                        self.segments.append( Segment(startAddr, ''.join(segmentdata)) )
                    startAddr = currentAddr = address
                    segmentdata = []
                for i in range(length):
                    segmentdata.append( chr(int(l[9+2*i:11+2*i],16)) )
                currentAddr = length + currentAddr
            elif type == 0x02:
                data=int(l[9:9+4],16)
                extSegAddr = 16 * data
                #print "2: Assign extSegAddr %x"%data
            elif type == 0x04:
                data=int(l[9:9+4],16)
                extSegAddr = 65536 * data
                #print "4: Assign extLinAddr %x"%data
                pass
            elif type == 0x03:
                data=int(l[9:9+length*2],16)
                self.applicationStartAddress=data
                pass
            elif type == 0x05:
                data=int(l[9:9+4*2],16)
                self.applicationStartAddress=data
                #print "5: Startaddr %x"%data
                pass
            elif type == 0x01: # EOF
                pass
            else:
                print "Ignored unknown field (type 0x%02x) in ihex file.\n" % type
        if segmentdata:
            self.segments.append( Segment(startAddr, ''.join(segmentdata)) )

    def loadFile(self, filename, fileobj=None):
        """fill memory with the contents of a file. file type is determined from extension"""
        close = 0
        if fileobj is None:
            fileobj = open(filename, "rb")
            close = 1
        try:
            #first check extension
            try:
                if filename[-4:].lower() == '.txt':
                    self.loadTIText(fileobj)
                    return
                elif filename[-4:].lower() in ('.a43', '.hex'):
                    self.loadIHex(fileobj)
                    return
                elif filename[-5:].lower() in ('.srec'):
                    self.loadSRec(fileobj)
                    return
            except FileFormatError:
                pass #do contents based detection below
            #then do a contents based detection
            try:
                self.loadELF(fileobj)
            except elf.ELFException:
                fileobj.seek(0)
                try:
                    self.loadIHex(fileobj)
                except FileFormatError:
                    fileobj.seek(0)
                    try:
                        self.loadTIText(fileobj)
                    except FileFormatError:
                        raise FileFormatError('file could not be loaded (not ELF, Intel-Hex, or TI-Text)')
        finally:
            if close:
                fileobj.close()

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    def saveIHex(self, filelike):
        """write a string containing intel hex to given file object"""
        noeof=0
        for seg in self.segments:
            address = seg.startaddress
            data    = seg.data
            start = 0
            while start<len(data):
                end = start + 16
                if end > len(data): end = len(data)
                filelike.write(self._ihexline(address, data[start:end]))
                start += 16
                address += 16
        filelike.write(self._ihexline(0, [], end=1))   #append no data but an end line
    
    def _ihexline(self, address, buffer, end=0):
        """internal use: generate a line with intel hex encoded data"""
        out = []
        if end:
            type = 1
        else:
            type = 0
        out.append( ':%02X%04X%02X' % (len(buffer),address&0xffff,type) )
        sum = len(buffer) + ((address>>8)&255) + (address&255) + (type&255)
        for b in [ord(x) for x in buffer]:
            out.append('%02X' % (b&255) )
            sum += b&255
        out.append('%02X\r\n' %( (-sum)&255))
        return ''.join(out)
    
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    
    def getMemrange(self, fromadr, toadr):
        """get a range of bytes from the memory. unavailable values are filled with 0xff."""
        res = ''
        toadr = toadr + 1   #python indexes are excluding end, so include it
        while fromadr < toadr:
            for seg in self.segments:
                segend = seg.startaddress + len(seg.data)
                if seg.startaddress <= fromadr and fromadr < segend:
                    if toadr > segend:   #not all data in segment
                        catchlength = segend - fromadr
                    else:
                        catchlength = toadr - fromadr
                    res = res + seg.data[fromadr-seg.startaddress : fromadr-seg.startaddress+catchlength]
                    fromadr = fromadr + catchlength    #adjust start
                    if len(res) >= toadr-fromadr:
                        break   #return res
            else:   #undefined memory is filled with 0xff
                res = res + chr(255)
                fromadr = fromadr + 1 #adjust start
        return res

    def getMem(self, address, size):
        """get a range of bytes from the memory. a ValueError is raised if
           unavailable addresses are tried to read"""
        data = []
        for seg in self.segments:
            #~ print "0x%04x  " * 2 % (seg.startaddress, seg.startaddress + len(seg.data))
            if seg.startaddress <= address and seg.startaddress + len(seg.data) >= address:
                #segment contains data in the address range
                offset = address - seg.startaddress
                length = min(len(seg.data)-offset, size)
                data.append(seg.data[offset:offset+length])
                address += length
        value = ''.join(data)
        if len(value) != size:
            raise ValueError("could not collect the requested data")
        return value
    
    def setMem(self, address, contents):
        """write a range of bytes to the memory. a segment covering the address
           range to be written has to be existent. a ValueError is raised if not
           all data could be written (attention: a part of the data may have been
           written!)"""
        #~ print "%04x: %r" % (address, contents)
        for seg in self.segments:
            #~ print "0x%04x  " * 3 % (address, seg.startaddress, seg.startaddress + len(seg.data))
            if seg.startaddress <= address and seg.startaddress + len(seg.data) >= address:
                #segment contains data in the address range
                offset = address - seg.startaddress
                length = min(len(seg.data)-offset, len(contents))
                seg.data = seg.data[:offset] + contents[:length] + seg.data[offset+length:]
                contents = contents[length:]    #cut away what is used
                if not contents: return         #stop if done
                address += length
        raise ValueError("could not write all data")
