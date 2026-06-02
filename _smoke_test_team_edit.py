"""Throwaway smoke test for editing a team member's name/email.
Creates a temp business + owner + member, calls the real update_business_member
handler, verifies People name/email update and the email-clash 409, then cleans up.
Run: python _smoke_test_team_edit.py
"""
import datetime
from types import SimpleNamespace

import main  # noqa: F401  -- confirms the FastAPI app imports with the edits
import models
from database import SessionLocal
from fastapi import HTTPException
from routers.auth import update_business_member, BusinessMemberUpdateRequest

STAMP = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
db = SessionLocal()
created = {"people": [], "access": [], "business": None}

def mk_person(first, last, email):
    p = models.People(
        PeopleFirstName=first, PeopleLastName=last, PeopleEmail=email,
        PeoplePassword="", PeopleActive=1, accesslevel=0, Subscriptionlevel=0,
        PeopleCreationDate=datetime.datetime.utcnow(),
    )
    db.add(p); db.flush(); created["people"].append(p.PeopleID); return p

def mk_access(biz, pid, level, role):
    a = models.BusinessAccess(
        BusinessID=biz, PeopleID=pid, AccessLevelID=level, Active=1,
        CreatedAt=datetime.datetime.utcnow(), Role=role,
    )
    db.add(a); db.flush(); created["access"].append(a.BusinessAccessID); return a

try:
    print("[setup] app imported OK")
    biz = models.Business(BusinessName=f"ZZ_SMOKE_{STAMP}")
    db.add(biz); db.flush(); created["business"] = biz.BusinessID
    owner = mk_person("ZZOwner", "Test", f"zz_owner_{STAMP}@example.com")
    mk_access(biz.BusinessID, owner.PeopleID, 3, "Owner")
    member = mk_person("OldFirst", "OldLast", f"zz_member_{STAMP}@example.com")
    member_access = mk_access(biz.BusinessID, member.PeopleID, 2, "Staff")
    db.commit()
    print(f"[setup] business={biz.BusinessID} owner={owner.PeopleID} member={member.PeopleID} access={member_access.BusinessAccessID}")

    cur = SimpleNamespace(PeopleID=owner.PeopleID)

    # --- Happy path: change name + email + role ---
    new_email = f"zz_member_new_{STAMP}@example.com"
    res = update_business_member(
        member_access.BusinessAccessID,
        BusinessMemberUpdateRequest(
            PeopleFirstName="NewFirst", PeopleLastName="NewLast",
            PeopleEmail=new_email.upper(), Role="Manager",
        ),
        db=db, current_user=cur,
    )
    print("[happy] response:", res)
    db.expire_all()
    row = db.query(models.People).filter(models.People.PeopleID == member.PeopleID).first()
    assert row.PeopleFirstName == "NewFirst", row.PeopleFirstName
    assert row.PeopleLastName == "NewLast", row.PeopleLastName
    assert row.PeopleEmail == new_email, row.PeopleEmail  # normalized to lowercase
    assert res["Role"] == "Manager", res
    print("[happy] PASS — name/email/role updated, email normalized to lowercase")

    # --- Clash path: setting email to the owner's existing email must 409 ---
    try:
        update_business_member(
            member_access.BusinessAccessID,
            BusinessMemberUpdateRequest(PeopleEmail=owner.PeopleEmail),
            db=db, current_user=cur,
        )
        print("[clash] FAIL — expected 409 but no error raised"); raise SystemExit(1)
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
        print(f"[clash] PASS — got {e.status_code}: {e.detail}")

    # member email must be unchanged after the rejected clash
    db.expire_all()
    row = db.query(models.People).filter(models.People.PeopleID == member.PeopleID).first()
    assert row.PeopleEmail == new_email, row.PeopleEmail
    print("[clash] PASS — member email unchanged after rejected update")

    print("\nALL SMOKE TESTS PASSED")
finally:
    db.rollback()
    for aid in created["access"]:
        db.query(models.BusinessAccess).filter(models.BusinessAccess.BusinessAccessID == aid).delete()
    for pid in created["people"]:
        db.query(models.People).filter(models.People.PeopleID == pid).delete()
    if created["business"]:
        db.query(models.Business).filter(models.Business.BusinessID == created["business"]).delete()
    db.commit()
    db.close()
    print("[cleanup] removed throwaway rows")
