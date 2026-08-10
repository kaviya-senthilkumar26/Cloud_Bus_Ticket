# CloudBus - Cloud Bus Pass System

## Run locally

1. Open this folder in VS Code.
2. Activate/create the virtual environment:
   Windows:
   `python -m venv venv`
   `venv\Scripts\activate`
3. Install dependencies:
   `pip install -r requirements.txt`
4. Run:
   `python app.py`
5. Open:
   `http://127.0.0.1:5000`

## Important
- Every bus is standardized to 50 passenger seats.
- Driver position is separate and disabled.
- Available seats are white.
- Selected seats become green.
- Confirmed/booked seats are grey and disabled.
- Exact selected seat numbers are stored.
- Server validates the seats again during booking.
- Cancellation releases the booked seats.

## Make an admin
Register a normal account first, then run:

`python`

python
import sqlite3
conn = sqlite3.connect("bus_pass.db")
conn.execute("UPDATE users SET role='admin' WHERE email=?", ("your@email.com",))
conn.commit()
conn.close()
exit()


Then log in again.
