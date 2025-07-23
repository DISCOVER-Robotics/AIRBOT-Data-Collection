```bash
cd airbot_data_collection/airbot/schemas
flatc --python *.fbs
flatc -b --schema -o airbot_fbs/bfbs *.fbs
```
