import eg

eg.RegisterPlugin(
    name="Marantz M-CR511",
    author="Kevin Smith",
    version="0.0.7",
    kind="other",
    description="Control the Marantz M-CR511 amplifier via the TCP/IP control protocol"
)


#import the other modules
import socket
from select import select
from threading import Event, Thread, RLock
from time import sleep


class Amp(eg.PluginBase):

    def __init__(self):

        #actions
        group_Connection = self.AddGroup("Connection", "Connect and disconnect to/from Amplifier")
        group_Connection.AddAction(ConnectToAmp)
        group_Connection.AddAction(DisconnectFromAmp)

        group_TimerClock = self.AddGroup("Timer & Clock", "Set Timer, switch it On/Off and show the Clock")
        group_TimerClock.AddAction(TimerOn)
        group_TimerClock.AddAction(TimerOff)
        group_TimerClock.AddAction(Clock)

        group_Power = self.AddGroup("Power", "Actions regarding the Power State of the amplifier")
        group_Power.AddAction(PowerOn)
        group_Power.AddAction(PowerOff)
        group_Power.AddAction(MakeAmpReadyForMP)

        group_Vol = self.AddGroup("Volume", "Actions regarding the Volume")
        group_Vol.AddAction(VolUp)
        group_Vol.AddAction(VolDown)
        group_Vol.AddAction(NormalMode)
        group_Vol.AddAction(StadiumMode)
        group_Vol.AddAction(NightMode)
        group_Vol.AddAction(NextAudioMode)
        group_Vol.AddAction(NightModeIfNoStadiumMode)
        group_Vol.AddAction(SwitchBetweenNormalAndNightAudioMode)

        group_Other = self.AddGroup("Other", "Other Stuff")
        group_Other.AddAction(PrintCurrentParameters)
        group_Other.AddAction(Favourite)



        #available commands
        #TODO: Try out Favourites and request Favourites List
        self.commands = [
            ('PWON', "Power On"),
            ('PWOFF', "Power Off"),
            ('PW?', "Request Power Status"),

            ('MVUP', "Volume Up"),
            ('MVDOWN', "Volume Down"),
            ('MV[0-9][0-9]', "Volume %s"),
            ('MV?', "Request Volume Status"),
            ('MVVOAUP', "Volume Up"),
            ('MVVOADOWN', "Volume Down"),
            ('MVVOA[0-9][0-9]', "Volume %s"),
            ('MVVOA?', "Digital In"),

            ('MUON', "Mute"),
            ('MUOFF', "Mute Off"),
            ('MU?', "Request Mute Status"),
            ('MUVOAON', "Mute"),
            ('MUVOAOFF', "Mute Off"),
            ('MUVOA?', "Request Mute Status"),

            ('SIIRADIO', "Internet Radio"),
            ('SIBLUETOOTH', "Bluetooth"),
            ('SISERVER', "Server"),
            ('SIUSB', "USB"),
            ('SIREARUSB', "Rear USB"),
            ('SIDIGITALIN1', "Digital In"),
            ('SIANALOGIN', "Analog In"),

            ('SLPOFF', "Sleep Off"),
            ('SLP[0-9][0-9][0-9]', "Sleep %s"),
            ('SLP?', "Request Sleep Status"),

            ('TSONCE @**##-@$$%% [F] [N] VV O', "Timer Once Off"),
            ('TEVERY @**##-@$$%% [F] [N] VV O', "Timer Every Off"),
            ('TSONCE @**##-@$$%% [F] [N] VV O', "Timer Once set to %s "),
            ('TEVERY @**##-@$$%% [F] [N] VV O', "Timer Every set to %s "),

            ('CLK', "toggle Clock"),

            ('FV$$', "Favourite %s"),
            ('FVMEM [0-9][0-9]', "Set to Favourite %s"),
            ('FVDEL [0-9][0-9]', "Delete Favourite %s"),
            ('FV?', "Request Favourite List"),

            ('PSBAS UP', "Bass Up"),
            ('PSBAS DOWN', "Bass Down"),
            ('PSBAS [0-9][0-9]', "Set Bass to %s"),
            ('PSBAS ?', "Request Bass Level"),
            ('PSTRE UP', "Treble Up"),
            ('PSTRE DOWN', "Treble Down"),
            ('PSTRE [0-9][0-9]', "Set Treble to %s"),
            ('PSTRE ?', "Request Treble Level"),
            ('PSBAL LEFT', "Balance left"),
            ('PSBAL RIGHT', "Balance right"),
            ('PSBAL [0-9][0-9]', "Set Balance to %s"),
            ('PSBAL ?', "Request Balance Level"),
            ('PSSDB ON', "Dynamic Bass Boost On"),
            ('PSSDB OFF', "Dynamic Bass Boost Off"),
            ('PSSDB ?', "Request Dynamic Bass Boost Status"),
            ('PSSDI ON', "Source Direct On"),
            ('PSSDI OFF', "Source Direct Off"),
            ('PSSDI ?', "Request Source Direct Status")
        ]
        self.commands_strings = [entry[0] for entry in self.commands]

    def __start__(self, myString_test):
        print "starting" + myString_test

        self.status_variables = {
            "Power": None,
            "Input": "N/A",
            "Volume": None,
            "Mute": None,
            "SourceDirect": None,
            "Treble": None,
            "Bass": None,
            "Balance": None,
            "Timer": (None, None), #(once, every)
            "DynamicBassBoost": None,
            "Sleep": None,
            "AudioMode": None,   # 0 is Normal, 1 is Night, 2 is Stadium
            "ConnectStatus": 0
        }

        # a dictionary for values which cannot be set at the moment of the command, because the amplifier is switched off
        self.remember = {}

        self.start_connection()


    def __stop__(self):
        print "stopping plugin"
        self.stop_connection()

    def __close__(self):
        print "closing plugin"

    def start_connection(self):

        #initiate the socket & lock
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sockLock = RLock()

        #connect to the amplifier
        #TODO: have the IP address as an input parameter
        host = "192.168.1.197"
        port = 23
        self.sock.connect((host, port))

        # Start the Thread for Receiving
        self.stopThreadEvent = Event()
        thread = Thread(
            target=self.ThreadLoop,
            args=(self.stopThreadEvent, )
        )
        thread.start()

        self.status_variables["ConnectStatus"] = 1

        self.request_status_variables_update()

    def stop_connection(self):
        #stop the ThreadLoop
        self.stopThreadEvent.set()
        #shut down the socket connection
        self.sock.close()

        self.status_variables["ConnectStatus"] = 0
        print "done"

    def Configure(self, myString_test="", IP_str="192.168.1.197", TimerTimeEnd="0740"):
        panel = eg.ConfigPanel()
        textControl = wx.TextCtrl(panel, -1, myString_test)
        IP_str_Control2 = wx.TextCtrl(panel, -1, IP_str)
        textControl3 = wx.TextCtrl(panel, -1, TimerTimeEnd)

        panel.AddLine("Starting string ",textControl)
        panel.AddLine("IP address: ",IP_str_Control2)
        panel.AddLine("Text field 3: ",textControl3)

        while panel.Affirmed():
            panel.SetResult(textControl.GetValue(),
                IP_str_Control2.GetValue(),
                textControl3.GetValue()
            )

    def ThreadLoop(self, stopThreadEvent):
        while not stopThreadEvent.isSet():
            received_data_in_cur_round = False  #if we received data, we do not want to wait for the next round
            self.sockLock.acquire()
            readable, writable, exceptional = select([self.sock], [], [self.sock], 0)
            if readable:
                receive_data = self.sock.recv(1024)
                self.sockLock.release()
                received_data_in_cur_round = True
                receive_data = receive_data.split("\r")
                for msg in receive_data:
                    if not msg:
                        continue #only messages with content
                    self.handle_rcv_content(msg)
            else:
                self.sockLock.release()

            if exceptional:
                print "error in socket"
                print exceptional

            if not received_data_in_cur_round:
                stopThreadEvent.wait(0.1)

    #define a function to handle responses
    def receive_responses(self, exp_nb_responses=1):
        #try four times (last try has to be after some time t>200milliseconds)
        #after exp_nb_responses or more responses the cycle breaks
        n_responses = 0
        for recvTry in range(4):
            readable, writable, exceptional = select([self.plugin.sock], [], [self.plugin.sock], 0)
            if readable:
                receive_data = self.sock.recv(1024)
                receive_data = receive_data.split("\r")
                for msg in receive_data:
                    if not msg:
                        continue #only messages with content
                    self.handle_rcv_content(msg)
                    print msg
                    n_responses += 1
                if n_responses >= exp_nb_responses:
                    break
            sleep(0.07)
        sleep(0.01)     #TODO: test why this sleep statement is necessary (so that all messages get received through this fct, instead of the thread

    def handle_rcv_content(self, msg):
        print msg

        if msg.startswith("MVVOA"):
            self.status_variables["Volume"] = int(msg[5:7])
            self.TriggerEvent("Vol.", payload=str(self.status_variables["Volume"]))
        elif msg.startswith("MV"):
            self.status_variables["Volume"] = int(msg[2:4])
            self.TriggerEvent("Vol.", payload=str(self.status_variables["Volume"]))

        elif msg.startswith("MU"):
            if msg == "MUON":
                self.status_variables["Mute"] = True
            elif msg == "MUOFF":
                self.status_variables["Mute"] = False
            #trigger Event
            self.TriggerEvent("Mute.", payload=str(self.status_variables["Mute"]))

        elif msg.startswith("PW"):
            if msg == "PWON":
                self.status_variables["Power"] = True
                if len(self.remember) > 0:
                    self.execute_remembered_values()
            elif msg == "PWSTANDBY":
                self.status_variables["Power"] = False
            #trigger Event
            self.TriggerEvent("Power." + str(self.status_variables["Power"]))

        elif msg.startswith("SI"):
            if msg == "SIIRADIO":
                self.status_variables["Input"] = "Internet Radio"
            elif msg == "SIBLUETOOTH":
                self.status_variables["Input"] = "Bluetooth"
            elif msg == "SISERVER":
                self.status_variables["Input"] = "Server"
            elif msg == "SIUSB":
                self.status_variables["Input"] = "USB"
            elif msg == "SIREARUSB":
                self.status_variables["Input"] = "Rear USB"
            elif msg == "SIDIGITALIN1":
                self.status_variables["Input"] = "MP Lounge"
            elif msg == "SIANALOGIN":
                self.status_variables["Input"] = "Analog In"
            #trigger Event
            self.TriggerEvent("Input", payload=self.status_variables["Input"])

        elif msg.startswith("PS"):
            if msg.startswith("PSTRE"):
                self.status_variables["Treble"] = int(msg[6:8])
            elif msg.startswith("PSBAS"):
                self.status_variables["Bass"] = int(msg[6:8])
            elif msg.startswith("PSBAL"):
                self.status_variables["Balance"] = int(msg[6:8])
            elif msg.startswith("PSSDB"):
                if msg == "PSSDB ON":
                    self.status_variables["DynamicBassBoost"] = True
                elif msg == "PSSDB OFF":
                    self.status_variables["DynamicBassBoost"] = False
            elif msg.startswith("PSSDI"):
                if msg == "PSSDI ON":
                    self.status_variables["SourceDirect"] = True
                elif msg == "PSSDI OFF":
                    self.status_variables["SourceDirect"] = False

        elif msg.startswith("SLP"):
            if msg.startswith("SLPOFF"):
                self.status_variables["Sleep"] = 0
            else:
                self.status_variables["Sleep"] = int(msg[3:6])
            #trigger Event
            self.TriggerEvent("SLP", payload=str(self.status_variables["Sleep"]))

    def execute_remembered_values(self):
        if "AudioMode" in self.remember:
            self.activateAudioMode(self.remember["AudioMode"])
            self.remember.pop("AudioMode", None)
        if len(self.remember) > 0:
            print "there are remembered values which have not been executed"

    def request_status_variables_update(self):
        #TODO: Check how large the buffer is (and how it interacts with the 1024 recv length). Maybe need to do a sockLock pause
        with self.sockLock:
            self.sock.sendall(b'PW?\r')
            self.sock.sendall(b'SI?\r')
            self.sock.sendall(b'MV?\r')
            self.sock.sendall(b'MU?\r')
            self.sock.sendall(b'PSSDI ?\r')
            self.sock.sendall(b'PSBAS ?\r')
            self.sock.sendall(b'PSTRE ?\r')
            self.sock.sendall(b'PSBAL ?\r')
            self.sock.sendall(b'PSSDB ?\r')
            self.sock.sendall(b'SLP?\r')
            self.sock.sendall(b'TS?\r') #TODO: Check Timer request command

    def activateAudioMode(self, mode):
        #first check whether the AudioMode is already active. If yes, then nothing has to be done
        if not (self.status_variables["AudioMode"] == mode):
            #check if the Power is On, if not, then we cannot change the Audio Mode. In this case, we remember, that we need to set it as soon as the amplifier is switched on again.
            if not self.status_variables["Power"]:
                self.remember["AudioMode"] = mode
            else:
                if mode == 0:   #normal
                    with self.sockLock:
                        self.sock.sendall(b'PSSDI ON\r')
                        self.sock.sendall(b'SSDIM100\r')
                        self.sock.sendall(b'PSBAS 50\r')
                        self.sock.sendall(b'PSTRE 50\r')
                        self.sock.sendall(b'PSBAL 50\r')
                        self.sock.sendall(b'PSSDB OFF\r')
                    self.status_variables["AudioMode"] = 0

                elif mode == 1:     #night
                    with self.sockLock:
                        self.sock.sendall(b'PSSDI OFF\r')
                        self.sock.sendall(b'PSBAS 40\r')
                        self.sock.sendall(b'PSTRE 52\r')
                        self.sock.sendall(b'SSDIM050\r')
                    self.status_variables["AudioMode"] = 1

                elif mode == 2:     #stadium
                    with self.sockLock:
                        self.sock.sendall(b'PSSDI OFF\r')
                        self.sock.sendall(b'PSBAS 52\r')
                        self.sock.sendall(b'PSTRE 58\r')
                        self.sock.sendall(b'SSDIM050\r')
                    self.status_variables["AudioMode"] = 2

        #trigger Event
        self.TriggerEvent("AudioMode", payload=str(self.status_variables["AudioMode"]))

    def switchToNextAudioMode(self):
        if self.status_variables["AudioMode"] is None:
            self.activateAudioMode(0)
        else:
            newAudioMode = (self.status_variables["AudioMode"] + 1) % 3
            self.activateAudioMode(newAudioMode)

    def sendCommand(self, cmd):
        with self.sockLock:
            self.sock.sendall(cmd)


###########
## Actions
###########

#
# Connection
#
class ConnectToAmp(eg.ActionBase):
    def __call__(self):
        sleep(5)       #seems to work with 10seconds
        self.plugin.start_connection()


class DisconnectFromAmp(eg.ActionBase):
    def __call__(self):
        self.plugin.stop_connection()


#
# Power
#
class PowerOn(eg.ActionBase):
    def __call__(self):
        if not self.plugin.status_variables["Power"]:
            with self.plugin.sockLock:
                self.plugin.sendCommand(b'PWON\r')
                sleep(3)


class PowerOff(eg.ActionBase):
    def __call__(self):
        if self.plugin.status_variables["Power"]:
            self.plugin.sendCommand(b'PWOFF\r')
            sleep(2)


class MakeAmpReadyForMP(eg.ActionBase):
    def __call__(self):
        if not self.plugin.status_variables["Power"]:
            self.plugin.sendCommand(b'PWON\r')
            sleep(4)
        if not self.plugin.status_variables["Input"] == "MP Lounge":
            self.plugin.sendCommand(b'SIDIGITALIN1\r')


#
# Volume & Tone Actions
#
class VolUp(eg.ActionBase):
    def __call__(self):
        self.plugin.sendCommand(b'MVUP\r')


class VolDown(eg.ActionBase):
    def __call__(self):
        self.plugin.sendCommand(b'MVDOWN\r')


class NormalMode(eg.ActionBase):
    def __call__(self):
        self.plugin.activateAudioMode(0)


class NightMode(eg.ActionBase):
    def __call__(self):
        self.plugin.activateAudioMode(1)


class StadiumMode(eg.ActionBase):
    def __call__(self):
        self.plugin.activateAudioMode(2)


class NextAudioMode(eg.ActionBase):
    def __call__(self):
        self.plugin.switchToNextAudioMode()


class SwitchBetweenNormalAndNightAudioMode(eg.ActionBase):
    def __call__(self):
        if self.plugin.status_variables["AudioMode"] == 0:
            self.plugin.activateAudioMode(1)
        else:
            self.plugin.activateAudioMode(0)


class NightModeIfNoStadiumMode(eg.ActionBase):
    def __call__(self):
        if self.plugin.status_variables["AudioMode"] != 2:
            self.plugin.activateAudioMode(1)


#
# Timer & Clock
#
class TimerOn(eg.ActionBase):
    def __call__(self):
        self.plugin.sendCommand(b'TSEVERY A0730-A0735 FA01 09 1\r')


class TimerOff(eg.ActionBase):
    def __call__(self):
        self.plugin.sendCommand(b'TSEVERY A0730-A0735 FA01 09 0\r')


class Clock(eg.ActionBase):
    def __call__(self):
        self.plugin.sendCommand(b'CLK\r')


#
# Favourites
#
class Favourite(eg.ActionBase):
    name = "Go to Favourite"
    description = "Go to a specified Favourite"

    def __call__(self, favouriteNb):
        cmd_str = b'FV %02d\r' %favouriteNb
        self.plugin.sendCommand(cmd_str)

    def Configure(self, favouriteNb=1):
        panel = eg.ConfigPanel()
        favouriteNbCtrl = panel.SpinIntCtrl(favouriteNb, max=50)
        panel.AddLine("Favourite Number:", favouriteNbCtrl)
        while panel.Affirmed():
            panel.SetResult(favouriteNbCtrl.GetValue())



#
# Read out Information
#
class ReadAmpDisplay(eg.ActionBase):
    def __call__(self):
        with self.plugin.sockLock:
            self.plugin.sendCommand(b'SI?\r')
            self.plugin.sendCommand(b'NSE\r')
            self.receive_responses(10)
            #TODO: add to action group


class PrintCurrentParameters(eg.ActionBase):
    def __call__(self):
        for variable in self.plugin.status_variables:
            print variable, ": ", self.plugin.status_variables[variable]


#TODO: read out the lines on Amplifier (esp for when Spotify/Bluetooth is playing)

#TODO: another thread which checks the connection to the amp every hour or so. If it is broken, then restart connection

