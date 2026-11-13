"""Create deterministic, fictional donor, donation, and notification datasets."""
import argparse,json,random
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import delete,func
from donor_api.database import Base,SessionLocal,engine
from donor_api.models import Donor,DonationHistory,DonorNotification
from data_apis.geo import location

GROUPS=["A+","A-","B+","B-","AB+","AB-","O+","O-"]
FIRST=["Aarav","Aditi","Akash","Anaya","Arjun","Diya","Ishaan","Kavya","Kabir","Meera","Neel","Nisha","Rohan","Sana","Tara","Vihaan"]
LAST=["Sharma","Rao","Patel","Nair","Das","Khan","Iyer","Mehta","Sen","Kulkarni","Reddy","Joshi","Menon","Kapoor","Ghosh","Shetty"]
def chunks(rows,size=5000):
    for i in range(0,len(rows),size):yield rows[i:i+size]

def generate(args):
    Path("data").mkdir(exist_ok=True);Base.metadata.create_all(engine);rng=random.Random(args.seed);today=args.as_of;now=datetime.combine(today,datetime.min.time(),tzinfo=timezone.utc);db=SessionLocal()
    try:
        if args.donors<1 or args.donation_records<0 or args.notification_records<0:raise SystemExit("donor count must be positive; history and notification counts cannot be negative")
        count=db.query(func.count(Donor.id)).scalar()
        if count and not args.reset:raise SystemExit("Donor database already contains records; pass --reset to replace the generated dataset.")
        if args.reset:
            for model in (DonorNotification,DonationHistory,Donor):db.execute(delete(model))
            db.commit()
        donation_counts=[args.donation_records//args.donors+(1 if i<args.donation_records%args.donors else 0) for i in range(args.donors)]
        donor_rows=[]; donations=[];consenting=[]
        for i in range(1,args.donors+1):
            loc=location(rng,i+args.blood_bank_offset);count=donation_counts[i-1]
            donation_dates=[today-timedelta(days=60+j*max(56,1500//max(1,count))) for j in range(count)]
            last_date=max(donation_dates) if donation_dates else None
            consent=rng.random()<.72
            row={**loc,"name":f"{FIRST[(i-1)%len(FIRST)]} {LAST[((i-1)//len(FIRST))%len(LAST)]} {i:06d}","age":rng.randint(18,65),"gender":rng.choice(["female","male","non_binary",None]),"blood_group":GROUPS[rng.randrange(8)],"phone":f"+91-00000-{i%100000:05d}","email":f"donor-{i:09d}@example.invalid","registration_date":today-timedelta(days=rng.randint(30,3650)),"last_donation_date":last_date,"donation_count":count,"available":rng.random()<.76,"preferred_contact_method":rng.choice(["email","sms","phone"]),"notification_consent":consent,"verification_status":rng.choices(["pending","verified","rejected"],[.15,.78,.07])[0],"eligibility_status":rng.choices(["pending_verification","eligible","temporarily_deferred","permanently_deferred"],[.16,.70,.12,.02])[0],"temporary_deferral_reason":None,"last_updated":now-timedelta(days=rng.randint(0,365))}
            if row["eligibility_status"]=="temporarily_deferred":row["temporary_deferral_reason"]=rng.choice(["self_reported_temporary_deferral","awaiting_clinical_review","temporary_medical_hold"])
            donor_rows.append(row)
            if consent:consenting.append(i)
            for donation_date in donation_dates:
                donations.append({"donor_id":i,"donation_date":donation_date,"blood_bank_id":1+rng.randrange(max(1,args.blood_bank_count)),"donation_type":rng.choice(["whole_blood","packed_red_blood_cells"]),"donation_status":"completed","units_collected":1,"next_eligible_date":None})
        for batch in chunks(donor_rows):db.execute(Donor.__table__.insert(),batch)
        db.commit()
        for batch in chunks(donations):db.execute(DonationHistory.__table__.insert(),batch)
        db.commit()
        if len(consenting)<args.notification_records:raise SystemExit("notification-records exceeds the number of consented donors")
        notification_rows=[]
        for i in range(args.notification_records):
            donor_id=consenting[i%len(consenting)]
            notification_rows.append({"donor_id":donor_id,"attempted_at":now-timedelta(days=rng.randint(0,730),minutes=rng.randint(0,1439)),"channel":rng.choice(["email","sms","phone"]),"status":rng.choice(["delivered","no_response","failed","responded"]),"consent_at_attempt":True,"response":rng.choice([None,"confirmed","declined","no_response"]),"request_reference":f"SYN-REQ-{i+1:08d}"})
        for batch in chunks(notification_rows):db.execute(DonorNotification.__table__.insert(),batch)
        db.commit()
        assert db.query(Donor).count()==args.donors
        assert db.query(DonationHistory).count()==args.donation_records
        assert db.query(DonorNotification).count()==args.notification_records
        # Verify the per-donor denormalized summary agrees with its persisted history.
        mismatch=db.query(Donor.id).outerjoin(DonationHistory).group_by(Donor.id).having(Donor.donation_count!=func.count(DonationHistory.id)).first()
        assert mismatch is None, f"donation count mismatch for donor {mismatch}"
        print(json.dumps({"seed":args.seed,"donors":args.donors,"donation_history":args.donation_records,"notification_records":args.notification_records,"blood_groups":GROUPS,"synthetic_contact_domain":"example.invalid"},indent=2))
    finally:db.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--seed",type=int,default=20261113);p.add_argument("--as-of",type=date.fromisoformat,default=date(2026,11,13));p.add_argument("--donors",type=int,default=100000);p.add_argument("--donation-records",type=int,default=50000);p.add_argument("--notification-records",type=int,default=30000);p.add_argument("--blood-bank-count",type=int,default=1000);p.add_argument("--blood-bank-offset",type=int,default=0);p.add_argument("--reset",action="store_true");generate(p.parse_args())
if __name__=="__main__":main()
