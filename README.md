### cs7ns4\_urbancomputing

## Offset for Phone Calculations: 82.75dB
I visited Chancery Park on 20 Oct 2026, between 12:30-12:50.<br>
I recorded the noise on my phone (dBFS), while polling the dB(A) sensor at the site.<br>
From this, I was able to calculate an offset of 82.75dB which will help me convert phone readings of dBFS into ordinary dB.<br>
This was only done on my phone.<br>
I cannot possibly ask all users to go calibrate their devices.<br>
Therefore 82.75dB be will applied to all dBFS readings that the application recieves, as a gold-standard.<br>
Chancery Park (DCC Monitor 11) is one of the noisier monitors on average, based on looking at DCC's Noise Monitor webiste.<br>
This makes the calibration suitable for my use-case of monitoring for urban environments.<br>
At the time of the calibration recording, there was heavy machinery in operation at Chancery Park, which may not be the most reflective of the city and may skew this calibration.<br>
<img width="656" height="360" alt="image" src="https://github.com/user-attachments/assets/570a8fc2-50f3-475d-a0bd-cc8d90c82844" />

# Run application
```
source .venv/bin/activate
python3 app.py
```

# Auxiliary Tests for Individual Files
## Run receiver for collected data

```
source .venv/bin/activate
python3 newReceiver.py
```
## Export my collected data from Firebase storage to CSV
```
source .venv/bin/activate
python3 getCSV.py
```
## Run poller for Dublin City Council open data API
```
source .venv/bin/activate
python3 newPoller.py
```
## ngrok URL - the website
`https://swapping-oncoming-joining.ngrok-free.dev`
to start the ngrok URL
```
ngrok http --url=swapping-oncoming-joining.ngrok-free.dev 8000
```
## userCalculations.py - get the user's own insights
```
python3 userCalculations.py TEST
```
replace TEST with real user tokens
## stationCalculations.py - get the insights for some XY coordinate's nearest DCC noise station
```
python3 stationCalculations.py 53.34385111946036 -6.255344078805972
```
replace dummy LAT/LONG with real user location
