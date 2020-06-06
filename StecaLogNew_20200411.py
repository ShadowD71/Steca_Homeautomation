#!/usr/bin/python
# -*- coding: utf-8 -*-
# Aufruf sudo python StecaLogNew_20200411.py /dev/ttyxxxx Baudrate True|False (OnlyPrint NOT send to VZ) True|False (Infinitemode)
# -------------------------------------------------------------------------------------------------
# -                                     NEUE VERSION                                              -
# -------------------------------------------------------------------------------------------------
# ToDo: 20200411 -> Startb. muss ermittelt werden. Dieses dann in der getData-Funkt. eintr. --> erl
# Mittels stty -F /dev/ttyUSB0 die eingestellten Parameter von USB0 herausfinden
# Falls die Baudrate nicht stimmt, diese mittels stty -F /dev/ttyUSB0 2400 einstellen
# Wenn alle Einstellungen stimmen, dann sollte screen /dev/ttyUSB0 2400 eine Ausgabe bringen.
# ACHTUNG!!!: Sollte der Endlosmodus nicht aktiv sein, dann muss ein Cronjob eingerichtet werden 
# mittels crontab -e (probieren, kann sein, das -e nicht funzt, da es nur für den Pi User ist, das
# Skript aber mittels sudo gestartet wird.)
# mittels pkill -f StecaLogNew_20200411.py kann das Skript beendet werden.
# um ein starten des Skripts mittels sudo zu unterbinden kann man den Pi User in die Gruppe dialout 
# integrieren. Somit hat der User Pi zugriff auf die serielle Schnittstelle.
# Befehl: sudo usermod -a -G dialout pi

# Aktuelles Gedankenexperiment: Skript startet ganz normal und prüft sich mittels ParallelThread selbst ob 
# es sich "aufgehangen" hat. Wenn ja, dann beendet sich das Skript von selbst und muss von extern neu ge-
# startet werden. Um dieses Experiment wirkungsvoll umzusetzen ist mittels CronJob/ext. Startskript alle 40 sek.
# zu prüfen, ob das Skript noch läuft, wenn JA, dann nicht neustarten, wenn NEIN, dann das Skript neustarten
# Um zu gewährleisten, das dieses Skript funktioniert, muss im lxterminal Autostart NICHT dieses Skript, 
# sondern start_steca.sh gestartet werden.

import serial
import sys
import urllib2
import time
import threading
import os, signal

# eMail
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.Utils import formatdate

class SendMail(object):
    
    ###############################################################################
    #                      DIESER BEREICH MUSS ANGEPASST WERDEN                   #
    ###############################################################################        
    mailadress = 'email@example.com'
    smtpserver = 'xxxxxx'
    username = 'xxxxx'
    password = 'xxxxx'

    def send(self):
        # Mail vorbereiten
        to = self.mailadress
        From = self.mailadress
        subject = 'StecaLog wurde am ' + self.getDateString() + ' um ' + self.getTimeString() + ' neu gestartet.'
        msg = self.prepareMail(From, to, subject)

        # Mit Server verbinden und Mail senden
        server = smtplib.SMTP(self.smtpserver)
        server.ehlo() # Hat irgendwas mit den zu sendenden Informationen zu tun
        server.starttls() # Benutze verschlüsselten SSL Modus
        server.ehlo() # Um starttls lauffähig zu bekommen
        server.login(self.username, self.password)
        failed = server.sendmail(From, to, msg.as_string())
        server.quit()

    def prepareMail(self, From, to, subject):
        msg = MIMEMultipart()
        msg['From'] = From
        msg['To'] = to
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject

        # Der Mailbody ist leer
        msg.attach( MIMEText("") )
        return msg
        
    def getTimeString(self):
        
        return time.strftime("%H:%M:%S", time.localtime())
 

    def getDateString(self):
        
        return time.strftime("%d.%m.%Y", time.localtime())

class Steca():
    
    def __init__(self, dev="/dev/ttyUSB0", baud=2400, onlyPrint=False, infinity=True):
        self.onlyPrint = onlyPrint  # Daten werden nicht gesendet
        self.infinity = infinity    # Programm läuft unendlich oder bis KBI
        self.device = dev           # übergebenes SerialDevice
        self.baudrate = baud        # übergebene Baudrate
        self.ser = None             
        self.aktDatensatz = 0       # Aktuell gesendeter Datensatz (Wichtig für den Paralleltask)
        self.PID = -1               # Skript PID (Damit Skript beendet werden kann)
        self.t = threading.Thread(name='SecureThread', target=self.checkAbort)
        self.goExecption = False
        self.mail = SendMail()
        self.aktMode = ""
        
        ###############################################################################
        #                      DIESER BEREICH MUSS ANGEPASST WERDEN                   #
        ###############################################################################        
        self.middleware = 'http://IP-Adresse/middleware/data/'
        self.s_uuid_NetzSpannung = 'dfacb280-68e1-11e8-a365-d91e0d538c32'
        self.s_uuid_NetzFrequenz = '26f94c20-68e2-11e8-b43c-2d2f24c86a92'
        self.s_uuid_ACAusgangsSpannung = '7131a340-68e2-11e8-97d2-99a34dce5585'
        self.s_uuid_ACAusgangsFrequenz = '9e6c6b40-68e2-11e8-a215-edb2ded058a8'
        self.s_uuid_ACScheinLeistung = '028ab700-68e3-11e8-9594-3724189266e4'
        self.s_uuid_ACWirkLeistung = '2f4042d0-68e3-11e8-a727-e7eace5856e2'
        self.s_uuid_AusgangsLast = 'a26c9b80-68e3-11e8-8204-176e9f4e279f'
        self.s_uuid_InterneBusSpannung = 'cc4cc560-68e3-11e8-bd6c-2fdc17fd79c8'
        self.s_uuid_BatterieSpannung = '3a458a80-68e4-11e8-8694-15376d86b9c5'
        self.s_uuid_BatterieLadeStrom = '7914f8f0-68e4-11e8-875c-eda0aea0556d'
        self.s_uuid_BatterieKapazitaet = 'd1e30cb0-68e4-11e8-9828-5da6ea7291f0'
        self.s_uuid_KuehlkoerperTemperatur = '13fdaa70-68e5-11e8-96f5-ed7a0f14b0bf'
        self.s_uuid_PVEingangsStrom = '467f8860-68e5-11e8-9f4b-75249ec0c98b'
        self.s_uuid_PVEingangsSpannung = '78f49220-68e5-11e8-bb60-7fa278f19fd9'
        self.s_uuid_BatterieSpannungLaderegler = 'c7ed7830-68e5-11e8-b16f-49f288e2a304'
        self.s_uuid_BatterieEntladeStrom = 'eec26b80-68e5-11e8-a462-277fe00ec109'
        self.s_uuid_PVLadeLeistung = '2f2608a0-68e6-11e8-999b-39b3dcd54355'
        self.s_uuid_Bypass_Batterie = 'c439c9e0-8148-11e8-8869-25685d91e85a'


        
    def print_inline2(string):
        # import sys ist nötig
        # diese Variante funktioniert bis Python2.7
        print("\r" + string),
        sys.stdout.flush()

#    def print_inline3(string):
#            # diese Variante ist für Python3
#            print("\r" + string, end="")



    def printMessage(self):
        print("Steca Seriallogger V1.5 (c) 2020 von P. Froberg (Project: HARPI)")
        print("Logging startet @ " + self.getTimeString())
        print("Aktuelle PID: " + str(self.PID))
        print("Aufrufparameter 1. Device, 2. Baudrate, 3. Debug True/False [opt], 4. Endlosmodus True/False [opt]")
        if self.infinity:
            print("Endlosmodus aktiv")
        else:
            print("Einzelmodus aktiv")
        print("Mittels CTRL + C kann das Skript unterbrochen werden!")
        

        
    def establishSerialConnection(self):
        try:
            self.ser = serial.Serial(self.device, self.baudrate)
            return True
        except serial.SerialException:
            print("[-] Serielle Verbindung konnte nicht hergestellt werden!")
            return False
            
        
        
    def file_get_contents(self, filename, use_include_path = 0, context = None, offset = -1, maxlen = -1):
        if (filename.find('://') > 0):
            ret = urllib2.urlopen(filename).read()
            return ret


        
    def getTimeString(self):
        return time.strftime("%Y-%m-%d_%H.%M.%S", time.localtime())

    
    
    def readMode(self):
        t = ""
        self.ser.flush()
        self.ser.write("QMOD\x49\xC1\x0D")
        time.sleep(2)
        byte_2 = self.ser.read()
        while byte_2 != chr(0x0D):
            t = t + byte_2
            byte_2 = self.ser.read()
        tmpmode = t.replace("(", "")
        aktMode = tmpmode[0:1:1]

        return aktMode
    
    
    
    def printReceivedData(self, SerData):
    	  s = str(SerData)
    	  print(s)	

        
        
    def sendData(self, SerData, TransmitTime, aktMode="x"):

        self.aktDatensatz = 0
        # Startzeit der Funktion ermitteln
        startTime = self.getTimeString() 

        # print(SerData)

        # Datenarray erstellen
        tmp = SerData.split(' ')
        
        s = "[+] ---------------------------------------------------------------------------------- " 
        print("\r" + s)
        s = "[+] ---------------------------------NEUER DATENSATZ---------------------------------- " 
        print("\r" + s)
        s = "[+] ---------------------------------------------------------------------------------- " 
        print("\r" + s)

        if self.aktMode == 'B':
            self.file_get_contents(self.middleware + self.s_uuid_Bypass_Batterie + '.json?operation=add&value=' + '70')
            s = "[+] Batteriemodus: \t\t\t" + self.aktMode + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            time.sleep(2)
            self.aktDatensatz += 1
        if self.aktMode == 'L':
            print("\r" + s)
            self.file_get_contents(self.middleware + self.s_uuid_Bypass_Batterie + '.json?operation=add&value=' + '20')
            s = "[+] Netzmodus: \t\t\t" + self.aktMode + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            time.sleep(2)
            self.aktDatensatz += 1

        if len(tmp) == 21:

            ###############################################################################
            #                      DIESER BEREICH MUSS ANGEPASST WERDEN                   #
            ###############################################################################        
            NSp = tmp[0]
            NetzSpannung = NSp #.replace("(", "")
            self.file_get_contents(self.middleware + self.s_uuid_NetzSpannung + '.json?operation=add&value=' + NetzSpannung)
            s = "[+] NetzSpannung: \t\t\t" + NetzSpannung + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)


            NetzFrequenz = tmp[1]
            self.file_get_contents(self.middleware + self.s_uuid_NetzFrequenz + '.json?operation=add&value=' + NetzFrequenz)
            s = "[+] NetzFrequenz: \t\t\t" + NetzFrequenz + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            ACAusgangsSpannung = tmp[2]
            self.file_get_contents(self.middleware + self.s_uuid_ACAusgangsSpannung + '.json?operation=add&value=' + ACAusgangsSpannung)
            s = "[+] ACAusgangsSpannung: \t\t" + ACAusgangsSpannung + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            ACAusgangsFrequenz = tmp[3]
            self.file_get_contents(self.middleware + self.s_uuid_ACAusgangsFrequenz + '.json?operation=add&value=' + ACAusgangsFrequenz)
            s = "[+] ACAusgangsFrequenz: \t\t" + ACAusgangsFrequenz + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            ACScheinLeistung = tmp[4]
            self.file_get_contents(self.middleware + self.s_uuid_ACScheinLeistung + '.json?operation=add&value=' + ACScheinLeistung)
            s = "[+] ACScheinLeistung: \t\t\t" + ACScheinLeistung + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)


            ACWirkLeistung = tmp[5]
            self.file_get_contents(self.middleware + self.s_uuid_ACWirkLeistung + '.json?operation=add&value=' + ACWirkLeistung)
            s = "[+] ACWirkLeistung: \t\t\t" + ACWirkLeistung + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            AusgangsLast = tmp[6]
            self.file_get_contents(self.middleware + self.s_uuid_AusgangsLast + '.json?operation=add&value=' + AusgangsLast)
            s = "[+] AusgangsLast: \t\t\t" + AusgangsLast + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            InterneBusSpannung = tmp[7]
            self.file_get_contents(self.middleware + self.s_uuid_InterneBusSpannung + '.json?operation=add&value=' + InterneBusSpannung)
            s = "[+] InterneBusSpannung: \t\t" + InterneBusSpannung + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            BatterieSpannung = tmp[8]
            self.file_get_contents(self.middleware + self.s_uuid_BatterieSpannung + '.json?operation=add&value=' + BatterieSpannung)
            s = "[+] BatterieSpannung: \t\t\t" + BatterieSpannung + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            BatterieLadeStrom = tmp[9]
            self.file_get_contents(self.middleware + self.s_uuid_BatterieLadeStrom + '.json?operation=add&value=' + BatterieLadeStrom)
            s = "[+] BatterieLadeStrom: \t\t\t" + BatterieLadeStrom + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            BatterieKapazitaet = tmp[10]
            self.file_get_contents(self.middleware + self.s_uuid_BatterieKapazitaet + '.json?operation=add&value=' + BatterieKapazitaet)
            s = "[+] BatterieKapazitaet: \t\t" + BatterieKapazitaet + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            KuehlkoerperTemperatur = tmp[11]
            self.file_get_contents(self.middleware + self.s_uuid_KuehlkoerperTemperatur + '.json?operation=add&value=' + KuehlkoerperTemperatur)
            s = "[+] KuehlkoerperTemperatur: \t\t" + KuehlkoerperTemperatur + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            PVEingangsStrom = tmp[12]
            self.file_get_contents(self.middleware + self.s_uuid_PVEingangsStrom + '.json?operation=add&value=' + PVEingangsStrom)
            s = "[+] PVEingangsStrom: \t\t\t" + PVEingangsStrom + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            PVEingangsSpannung = tmp[13]
            self.file_get_contents(self.middleware + self.s_uuid_PVEingangsSpannung + '.json?operation=add&value=' + PVEingangsSpannung)
            s = "[+] PVEingangsSpannung: \t\t" + PVEingangsSpannung + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            BatterieSpannungLaderegler = tmp[14]
            self.file_get_contents(self.middleware + self.s_uuid_BatterieSpannungLaderegler + '.json?operation=add&value=' + BatterieSpannungLaderegler)
            s = "[+] BatterieSpannungLaderegler: \t" + BatterieSpannungLaderegler + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            BatterieEntladeStrom = tmp[15]
            self.file_get_contents(self.middleware + self.s_uuid_BatterieEntladeStrom + '.json?operation=add&value=' + BatterieEntladeStrom)
            s = "[+] BatterieEntladeStrom: \t\t" + BatterieEntladeStrom + " \t\tStartzeit: " + str(self.getTimeString())	
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)

            PVLadeLeistung = tmp[19]
            self.file_get_contents(self.middleware + self.s_uuid_PVLadeLeistung + '.json?operation=add&value=' + PVLadeLeistung)		
            s = "[+] PVLadeLeistung: \t\t\t" + PVLadeLeistung + " \t\tStartzeit: " + str(self.getTimeString())
            print("\r" + s)
            self.aktDatensatz += 1
            time.sleep(2)


    # Paralleltask prüft ob Skript beendet werden muss
    def checkAbort(self):
        print("[+] Starte Absturzüberwachung ... \r")
        aktData = self.aktDatensatz                 # Aktuell gesendeten Datensatz zwischenspeichern

        while True:                                 # Endlos prüfen
            time.sleep(10)                          # Alle 10 Sekunden
            if aktData == self.aktDatensatz:        # Wenn der aktuelle Datennsatz sich nach 10 Sek nicht geändert hat, dann ENDE
                print("\r[-] Sende Mail ... ")
                self.mail.send()
                print("\r[-] Verbindungsfehler zum Volkszähler aufgetreten, Fehler abgefangen, Skript wird beendet.")
                os.kill(self.PID, signal.SIGTERM)
            else:
                aktData = self.aktDatensatz         # ansonsten weiter

            
    def getData(self, onlyPrint, infinity):
        
        try:
            
            # Wenn Endlosmodus aktiv ...
            if infinity:
                
                # ... dann solange lesen, bis KeyBoardInterrupt ausgelöst wird
                while 1:

                    # Ausgabestring löschen
                    s = ""
                    self.ser.flush()
                    # Anforderung der Werte an den Steca senden
                    self.ser.write("QPIGS\xB7\xA9\x0D")
                    # Zwei Sekunden warten 
                    time.sleep(2)
                    # Erstes Byte lesen
                    byte = self.ser.read()

                    # Wenn es das Startbyte ist, dann ...
                    if byte == chr(0x28): #PF# Startbyte

                        byte = self.ser.read()
                        # ... solange von der seriellen Schnittstelle lesen, bis "Endebyte" kommt
                        while byte != chr(0x0D):
                            s = s + byte
                            byte = self.ser.read()
                        # Wenn alles gelesen, dann senden ...    
                        if not onlyPrint:
                            # String vor dem senden um zwei Bytes kürzen, das ist die CRC Antwort des Steca
                            self.sendData(s[:-2], time.time())
                        else:
                            # ... oder nur ausgeben
                            print("[+] DEBUG: Daten werden nur ausgegeben, aber NICHT gesendet!")
                            # String vor dem ausgeben um zwei Bytes kürzen, das ist die CRC Antwort des Steca
                            self.printReceivedData(s[:-2])
                        self.aktMode = self.readMode()		
                        
            # ... ansonsten ...            
            else:
                
                # ... nur einmal ausführen
                # Ausgabestring löschen
                s = ""
                self.ser.flush()
                # Anforderung der Werte an den Steca senden
                self.ser.write("QPIGS\xB7\xA9\x0D")
                # Zwei Sekunden warten 
                time.sleep(2)
                # Erstes Byte lesen
                byte = self.ser.read()

                # Wenn es das Startbyte ist, dann ...
                if byte == chr(0x28): #PF# Startbyte

                    byte = self.ser.read()
                    # ... solange von der seriellen Schnittstelle lesen, bis "Endebyte" kommt
                    while byte != chr(0x0D):
                        s = s + byte
                        byte = self.ser.read()
                    # Wenn alles gelesen, dann senden ...    
                    if not onlyPrint:
                        # String vor dem senden um zwei Bytes kürzen, das ist die CRC Antwort des Steca
                        self.sendData(s[:-2], time.time())
                    else:
                        # ... oder nur ausgeben
                        print("[+] DEBUG: Daten werden nur ausgegeben, aber NICHT gesendet!")
                        # String vor dem ausgeben um zwei Bytes kürzen, das ist die CRC Antwort des Steca
                        self.printReceivedData(s[:-2])
                    self.aktMode = self.readMode()		
				
        except KeyboardInterrupt:
            print("[+] Unterbrechung empfangen, Stoppe … Prozess endet in wenigen Sekunden.")
            
            
            
            
    def start(self):
        self.PID = os.getpid()
        self.printMessage()
        self.t.setDaemon(True)
        self.t.start()
        print("[+] Versuche serielle Verbindung herszustellen ... ")
        if self.establishSerialConnection():
            print("[+] Serielle Verbindung hergestellt. ")   
            if self.onlyPrint:
                print("[+] Hole Daten. (Achtung! Daten werden NICHT gesendet) ")   
            else:
                print("[+] Hole Daten.")
            self.getData(self.onlyPrint, self.infinity)
            
        
###############################################################################
#                      DIESER BEREICH MUSS ANGEPASST WERDEN                   #
###############################################################################                
S = Steca("/dev/ttyUSB0", "2400", False, True)
S.start()
        
        