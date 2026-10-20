### cs7ns4\_urbancomputing



## Run receiver for collected data

```
source .venv/bin/activate
python3 receiver.py

```

## Export my collected data from Firebase storage to CSV
```
source .venv/bin/activate
python3 getCSV.py
```
## Run poller for Dublin City Council open data API
```
source .venv/bin/activate
python3 poller.py
```

## ngrok URL for Assignment 4 (multiple user access)
`https://swapping-oncoming-joining.ngrok-free.dev`
to start the ngrok URL
```
ngrok http --url=swapping-oncoming-joining.ngrok-free.dev 8000
```

## TEMP: test userCalculations.py
```
python3 userCalculations.py TEST
```
replace TEST with real user tokens
calculations will eventually be instantiated by a Main file when the rest of the application is written, this is just to test that the core functionality of the user insights calculations is working

## TEMP: test stationCalculations.py
```
python3 stationCalculations.py 53.34385111946036 -6.255344078805972
```
replace LAT/LONG with real user location
calculations will eventually be instantiated by a Main file when the rest of the application is written, this is just to test that the core functionality of the station insights calculations is working

## Offset for Phone Calculations: 92.75dB
I visited Chancery Park on 20 Oct 2026, between 12:30-12:50.
I recorded the noise on my phone (dBFS), while polling the dB(A) sensor at the site.
From this, I was able to calculate an offset of 92.75dB which will help me convert phone readings of dBFS into ordinary dB.
This was only done on my phone.
I cannot possibly ask all users to go calibrate their devices.
Therefore 92.75dB be will applied to all dBFS readings that the application recieves, as a gold-standard.
Chancery Park (DCC Monitor 11) is one of the noisier monitors on average, based on looking at DCC's Noise Monitor webiste.
This makes the calibration suitable for my use-case of monitoring for urban environments.
At the time of the calibration recording, there was heavy machinery in operation at Chancery Park, which may not be the most reflective of the city and may skew this calibration.

