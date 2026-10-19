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

## TEMP: test calculations.py
```
python3 calculations.py TEST
```
replace TEST with real user tokens
calculations will eventually be instantiated by a Main file when the rest of the application is written, this is just to test that the core functionality of the user insights calculations is working