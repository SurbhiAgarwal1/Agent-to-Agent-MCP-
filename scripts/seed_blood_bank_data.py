"""Create deterministic, fictional blood-bank API data using batched inserts."""
import argparse, json, os, random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import delete, func
from data_apis.geo import location
from blood_bank_api.database import Base, SessionLocal, engine
from blood_bank_api.models import BloodBank, BloodInventory, BloodRequest, Hospital

GROUPS=["A+","A-","B+","B-","AB+","AB-","O+","O-"]
COMPONENTS=["whole_blood","packed_red_blood_cells"]
def chunks(rows,size=5000):
    for i in range(0,len(rows),size):yield rows[i:i+size]

def generate(args):
    Path("data").mkdir(exist_ok=True); Base.metadata.create_all(engine)
    db=SessionLocal(); rng=random.Random(args.seed)
    try:
        if args.blood_banks<1 or args.hospitals<1 or args.inventory_records<0 or args.historical_requests<0: raise SystemExit("bank and hospital counts must be positive; inventory and request counts cannot be negative")
        current=db.query(func.count(BloodBank.id)).scalar()
        if current and not args.reset: raise SystemExit("Blood bank database already contains records; pass --reset to replace the generated dataset.")
        if args.reset:
            for model in (BloodRequest,BloodInventory,BloodBank,Hospital):db.execute(delete(model))
            db.commit()
        required_inventory=args.blood_banks*len(GROUPS)*len(COMPONENTS)
        if args.inventory_records != required_inventory: raise SystemExit(f"inventory-records must equal blood-banks × 8 groups × 2 components ({required_inventory})")
        now=datetime.combine(args.as_of,datetime.min.time(),tzinfo=timezone.utc)
        bank_rows=[]
        for i in range(args.blood_banks):
            loc=location(rng,i)
            bank_rows.append({**loc,"name":f"{loc['city']} {['Community','Regional','Central','Civic'][i%4]} Blood Centre {i+1:04d}","registration_number":f"SYN-BB-{i+1:08d}","contact_number":f"+91-00000-{i%100000:05d}","contact_email":f"bank-{i+1:08d}@example.invalid","operating_hours":"24 hours" if i%5==0 else "08:00-20:00","emergency_available":i%5!=4,"verification_status":["verified","pending","under_review"][i%20==0 and 2 or i%8==0 and 1 or 0],"bank_type":["government","private","charitable","hospital_based"][i%4],"last_updated":now-timedelta(days=rng.randint(0,180))})
        for batch in chunks(bank_rows):db.execute(BloodBank.__table__.insert(),batch)
        db.commit()
        bank_ids=[x[0] for x in db.query(BloodBank.id).order_by(BloodBank.id).all()]
        inventory=[]
        for bank_id in bank_ids:
            for group in GROUPS:
                for component in COMPONENTS:
                    high, mode = ((90, 28) if component=="whole_blood" else (70, 22))
                    units=max(0,int(rng.triangular(0,high,mode)))
                    if rng.random()<.12:units=0
                    reserved=rng.randint(0,min(units,8))
                    expiry=now+timedelta(days=rng.randint(-5,42))
                    inventory.append({"blood_bank_id":bank_id,"blood_group":group,"component_type":component,"available_units":units,"reserved_units":reserved,"last_updated":now-timedelta(hours=rng.randint(0,720)),"expiry_date":expiry,"availability_status":"expired" if expiry<now else "available" if units>reserved else "out_of_stock"})
        for batch in chunks(inventory):db.execute(BloodInventory.__table__.insert(),batch)
        db.commit()
        hospital_rows=[]
        for i in range(args.hospitals):
            loc=location(rng,i+args.blood_banks)
            same_city=[b[0] for b in db.query(BloodBank.id).filter(BloodBank.city==loc["city"]).limit(3).all()]
            hospital_rows.append({**loc,"name":f"{loc['city']} {['General','District','Trauma','Community'][i%4]} Hospital {i+1:04d}","hospital_type":["public","private","charitable","teaching"][i%4],"emergency_contact":f"+91-00000-{(50000+i)%100000:05d}","contact_email":f"hospital-{i+1:08d}@example.invalid","associated_blood_bank_ids":json.dumps(same_city),"operating_status":"operational" if i%30 else "temporarily_closed"})
        for batch in chunks(hospital_rows):db.execute(Hospital.__table__.insert(),batch)
        db.commit()
        hospitals=db.query(Hospital.id,Hospital.city).order_by(Hospital.id).all(); bank_by_city={}
        for bid,city in db.query(BloodBank.id,BloodBank.city).all():bank_by_city.setdefault(city,[]).append(bid)
        request_rows=[]; start=now-timedelta(days=5*365)
        for i in range(args.historical_requests):
            hospital=hospitals[rng.randrange(len(hospitals))]; dt=start+timedelta(seconds=rng.randrange(5*365*86400)); priority=rng.choices(["normal","urgent","emergency"],[.55,.32,.13])[0]
            assigned=rng.sample(bank_by_city.get(hospital.city,bank_ids),k=min(rng.randint(0,2),len(bank_by_city.get(hospital.city,bank_ids))))
            request_rows.append({"hospital_id":hospital.id,"required_blood_group":GROUPS[rng.randrange(8)],"required_units":rng.randint(1,20),"component_type":COMPONENTS[rng.randrange(2)],"request_date":dt,"required_by":dt+timedelta(hours=rng.randint(1,48)),"priority":priority,"status":rng.choices(["pending","processing","fulfilled","partially_fulfilled","cancelled"],[.1,.1,.58,.14,.08])[0],"assigned_blood_bank_ids":json.dumps(assigned),"notes":"Synthetic historical scenario"})
        for batch in chunks(request_rows):db.execute(BloodRequest.__table__.insert(),batch)
        db.commit()
        assert db.query(BloodInventory).count()==args.inventory_records
        assert db.query(Hospital).count()==args.hospitals
        assert db.query(BloodRequest).count()==args.historical_requests
        assert all(db.query(BloodInventory.blood_group).filter(BloodInventory.blood_bank_id == bid).distinct().count()==8 for bid in bank_ids)
        assert db.query(BloodInventory).filter(BloodInventory.component_type.notin_(COMPONENTS)).count()==0
        assert all(db.query(BloodInventory.id).filter_by(blood_bank_id=bid).count()==16 for bid in bank_ids)
        print(json.dumps({"seed":args.seed,"blood_banks":len(bank_ids),"inventories":len(inventory),"hospitals":len(hospital_rows),"historical_requests":len(request_rows),"blood_groups":GROUPS,"components":COMPONENTS},indent=2))
    finally:db.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--seed",type=int,default=20261113);p.add_argument("--as-of",type=date.fromisoformat,default=date(2026,11,13));p.add_argument("--blood-banks",type=int,default=1000);p.add_argument("--inventory-records",type=int,default=16000);p.add_argument("--hospitals",type=int,default=500);p.add_argument("--historical-requests",type=int,default=20000);p.add_argument("--reset",action="store_true");generate(p.parse_args())
if __name__=="__main__":main()
