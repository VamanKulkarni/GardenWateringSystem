import time
import urequests
import network
import machine
import ntputils
import ntptime
import gc
import ujson

gc.collect()

api_key = '<my_api_key>'
channel_id = 0000
wifi_connected = False

fallback_flow_duration = 1
fallback_pulse_rate = 12

class Feed():
  def __init__(self):
    self.flow_duration_id = 1
    self.last_water_time_id = 3
    self.abort_id = 5
    self.health_id = 2
    self.pulse_rate_id = 4

    self.pulse_rate = 0
    self.flow_duration = 0  
    self.abort = 0
    self.health = 0
    self.last_water_time = None

def wifi_connect(maxtries=5):
  sta_if = network.WLAN(network.STA_IF)
  if not sta_if.isconnected():
    sta_if.active(True)
    sta_if.connect("<ssid>", "<passwd>")
    count = 0
    while not sta_if.isconnected() and count < maxtries:
      print("Connecting to WiFi ({0}...".format(count))
      count += 1
      time.sleep(3)
  print('Network config:', sta_if.ifconfig())
  if sta_if.isconnected():
    global wifi_connected
    wifi_connected = True

def has_internet():
  try:
    resp = urequests.request("HEAD", "http://jsonip.com/")
    return True
  except OSError as ex:
    print("Internet OFF ", ex)
    print(dir(OSError))
    print(dir(ex))
    return False


def init_feed():
  jresp = get_latest_feed()
  feed = Feed()
  feed.pulse_rate = int(jresp['field{}'.format(feed.pulse_rate_id)])
  feed.flow_duration = int(jresp['field{}'.format(feed.flow_duration_id)])
  lastField = 'field{}'.format(feed.last_water_time_id)
  if (jresp[lastField] != None):
    feed.last_water_time = int(jresp[lastField])
  return feed

def get_latest_feed():
  try:
    url = "http://api.thingspeak.com/channels/{}/feeds/last.json?api_key={}".format(channel_id, api_key)
    resp = urequests.request("GET", url)
    jresp = resp.json()
    return jresp
  except:
    print ("Couldn't fetch latest feed from cloud")

def post_feed(feed):
  try:
    gc.collect()
    url = "http://api.thingspeak.com/update.json"
    json_data = {
                  "field{}".format(feed.pulse_rate_id) : feed.pulse_rate,
                  "field{}".format(feed.flow_duration_id) : feed.flow_duration,
                  "field{}".format(feed.health_id) : feed.health,
                  "field{}".format(feed.last_water_time_id) : feed.last_water_time,
                  "api_key": api_key  
                }
    header = {'Content-Type' : 'application/json' }
    resp = urequests.post(url, json = json_data, headers=header)
    if (resp.status_code != 200):
      print("Failed to Post Feed\n{}".format(resp))
    gc.collect()
  except:
    print("Something went wrong while posting feed to cloud")

def water_plants(feed):
  water_pump = machine.Pin(0,machine.Pin.OUT,value=1)
  # Remember: For a Relay module low() triggers the relay
  water_pump.low()
  time.sleep(feed.flow_duration * 60)
  water_pump.high()
  feed.last_water_time = time.time()
  return feed


if __name__ == "__main__":
  try:
    water_pump = machine.Pin(0,machine.Pin.OUT,value=1)
    gc.collect()
    time.sleep(2)
    
    rtcdata = None
    rtc = machine.RTC()
    rtcmem = rtc.memory()
    if len(rtcmem) == 0:
      print('No data in RTC')
      # Board was hard reset. Probably because of power cut-off.
      # Wait for WiFi router to come up
      time.sleep(60)
    else:
      rtcdata = ujson.loads(rtcmem)
    if rtcdata is None:
      rtcdata = {}

    feed = None
    fallback_feed = None
    cloud_feed = None
    # Attempt connecting to router
    wifi_connect()

    if wifi_connected and has_internet():
      cloud_feed = init_feed()
      ntputils.set_ntp_time(5)
      feed = cloud_feed 
    else:
      fallback_feed = Feed()
      fallback_feed.pulse_rate = fallback_pulse_rate
      fallback_feed.flow_duration = fallback_flow_duration  
      if rtcdata['lastwateringtime'] != None or rtcdata['lastwateringtime'] > 0: 
        # If you are here which implies that there is no internet access and
        # RTC is intact with current time
        fallback_feed.last_water_time = rtcdata['lastwateringtime']
      feed = fallback_feed
    gc.collect()
    waternow = False
    pulse_rate_in_secs = feed.pulse_rate * 60 * 60
    
    if feed.last_water_time is None:
      waternow = True
    elif feed.last_water_time + pulse_rate_in_secs <= time.time():
      waternow = True
    else:
      print ("SLEEPING..")

    if waternow:
      feed = water_plants(feed)
      gc.collect()
      rtcdata['lastwateringtime'] = feed.last_water_time
      if wifi_connected and has_internet():
        post_feed(feed)
      time.sleep(2)
    gc.collect()
    str = ujson.dumps(rtcdata)
    # Save to RTC memory
    rtc.memory(str)
    print("sleeping now for 30 mins")
    time.sleep(1800)
    gc.collect()
    print(gc.mem_free())
    feed.health = 1
    if wifi_connected and has_internet():
      post_feed(feed)
  finally:
    machine.reset()
