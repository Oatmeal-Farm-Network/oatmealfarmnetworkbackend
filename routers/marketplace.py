"""
routers/marketplace.py
Livestock Marketplace endpoints.

Mount in main.py:
    from routers import marketplace
    app.include_router(marketplace.router)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import get_db
import time, re

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

_cache: dict = {}
CACHE_TTL = 300
GCP_BUCKET_URL = "https://storage.googleapis.com/oatmeal-farm-network-images/Animals"

SLUG_TO_SPECIES_ID = {
    'alpacas': 2, 'bison': 9, 'buffalo': 34, 'camels': 18, 'cattle': 8,
    'chickens': 13, 'crocodiles': 25, 'dogs': 3, 'deer': 21, 'donkeys': 7,
    'ducks': 15, 'emus': 19, 'geese': 22, 'goats': 6, 'guinea-fowl': 26,
    'honey-bees': 23, 'horses': 5, 'llamas': 4, 'musk-ox': 27, 'ostriches': 28,
    'pheasants': 29, 'pigs': 12, 'pigeons': 30, 'quails': 31, 'rabbits': 11,
    'sheep': 10, 'snails': 33, 'turkeys': 14, 'yaks': 17,
}

SLUG_TO_LABEL = {
    'alpacas': 'Alpacas', 'bison': 'Bison', 'buffalo': 'Buffalo', 'camels': 'Camels',
    'cattle': 'Cattle', 'chickens': 'Chickens', 'crocodiles': 'Crocodiles & Alligators',
    'deer': 'Deer', 'dogs': 'Working Dogs', 'donkeys': 'Donkeys', 'ducks': 'Ducks',
    'emus': 'Emus', 'geese': 'Geese', 'goats': 'Goats', 'guinea-fowl': 'Guinea Fowl',
    'honey-bees': 'Honey Bees', 'horses': 'Horses', 'llamas': 'Llamas',
    'musk-ox': 'Musk Ox', 'ostriches': 'Ostriches', 'pheasants': 'Pheasants',
    'pigs': 'Pigs', 'pigeons': 'Pigeons', 'quails': 'Quails', 'rabbits': 'Rabbits',
    'sheep': 'Sheep', 'snails': 'Snails', 'turkeys': 'Turkeys', 'yaks': 'Yaks',
}

ANCESTRY_MAP = {
    'Full Peruvian':    "AND (a.PercentPeruvian='Full Peruvian' OR a.PercentPeruvian='FullPeruvian') ",
    'Partial Peruvian': "AND LEN(ISNULL(a.PercentPeruvian,''))>1 AND a.PercentPeruvian NOT IN ('Full Peruvian','FullPeruvian') ",
    'Full Chilean':     "AND (a.PercentChilean='Full Chilean' OR a.PercentChilean='FullChilean') ",
    'Partial Chilean':  "AND LEN(ISNULL(a.PercentChilean,''))>1 ",
    'Full Bolivian':    "AND (a.PercentBolivian='Full Bolivian' OR a.PercentBolivian='FullBolivian') ",
    'Partial Bolivian': "AND LEN(ISNULL(a.PercentBolivian,''))>1 ",
}

ACCOYO_MAP = {
    '1/8':        "AND a.Percentaccoyo IN ('1/8','1/4','3/8','1/2','5/8','3/4','7/8','FullAccoyo') ",
    '1/4':        "AND a.Percentaccoyo IN ('1/4','3/8','1/2','5/8','3/4','7/8','FullAccoyo') ",
    '3/8':        "AND a.Percentaccoyo IN ('3/8','1/2','5/8','3/4','7/8','FullAccoyo') ",
    '1/2':        "AND a.Percentaccoyo IN ('1/2','5/8','3/4','7/8','FullAccoyo') ",
    '5/8':        "AND a.Percentaccoyo IN ('5/8','3/4','7/8','FullAccoyo') ",
    '3/4':        "AND a.Percentaccoyo IN ('3/4','7/8','FullAccoyo') ",
    '7/8':        "AND a.Percentaccoyo IN ('7/8','FullAccoyo') ",
    'FullAccoyo': "AND a.Percentaccoyo='FullAccoyo' ",
}


def cache_get(key):
    e = _cache.get(key)
    return e['v'] if e and time.time() - e['t'] < CACHE_TTL else None


def cache_set(key, value):
    _cache[key] = {'v': value, 't': time.time()}


def _fix_photo(url):
    if not url:
        return None
    url = url.strip()
    matches = re.findall(r'https?://[^\s]+', url)
    url = matches[-1] if matches else url
    filename = url.split('/')[-1].strip()
    if not filename or len(filename) < 4:
        return None
    if filename.lower() in {'uploads', 'imagenotavailable.jpg', ''}:
        return None
    return f"{GCP_BUCKET_URL}/{filename}"


def _best_photo(row):
    for f in ['ListPageImage', 'Photo1', 'Photo2', 'Photo3', 'Photo4', 'Photo5']:
        v = getattr(row, f, None)
        if v:
            fixed = _fix_photo(str(v))
            if fixed:
                return fixed
    return None


def _safe_float(val):
    try:
        v = float(val)
        return v if v > 0 else None
    except Exception:
        return None


def _row_to_animal(row):
    breeds = [str(getattr(row, f, '') or '').strip()
              for f in ['Breed1', 'Breed2', 'Breed3', 'Breed4', 'Breed5']
              if getattr(row, f, None)]
    city = str(getattr(row, 'AddressCity', '') or '').strip()
    state = str(getattr(row, 'AddressState', '') or '').strip()
    location = ', '.join(filter(None, [city, state]))
    return {
        "animal_id": row.AnimalID,
        "people_id": getattr(row, 'PeopleID', None),
        "full_name": str(getattr(row, 'FullName', '') or '').strip(),
        "breeds": breeds,
        "location": location,
        "seller": str(getattr(row, 'BusinessName', '') or '').strip(),
        "photo": _best_photo(row),
        "price": _safe_float(getattr(row, 'Price', None)),
        "stud_fee": _safe_float(getattr(row, 'StudFee', None)),
        "dob_year": getattr(row, 'DOBYear', None),
    }


BASE_JOINS = """
    JOIN Pricing p ON a.AnimalID = p.AnimalID
    LEFT JOIN Photos ph ON a.AnimalID = ph.AnimalID
    LEFT JOIN SpeciesBreedLookupTable b  ON a.BreedID  = b.BreedLookupID
    LEFT JOIN SpeciesBreedLookupTable b2 ON a.BreedID2 = b2.BreedLookupID
    LEFT JOIN SpeciesBreedLookupTable b3 ON a.BreedID3 = b3.BreedLookupID
    LEFT JOIN SpeciesBreedLookupTable b4 ON a.BreedID4 = b4.BreedLookupID
    LEFT JOIN SpeciesBreedLookupTable b5 ON a.BreedID5 = b5.BreedLookupID
    LEFT JOIN BusinessAccess ba ON a.PeopleID = ba.PeopleID AND ba.Active = 1
    LEFT JOIN Business biz ON ba.BusinessID = biz.BusinessID
    LEFT JOIN Address addr ON biz.AddressID = addr.AddressID
"""

SELECT_COLS = """
    a.AnimalID, a.PeopleID, a.FullName, a.DOBYear,
    ph.Photo1, ph.Photo2, ph.Photo3, ph.Photo4, ph.Photo5,
    ph.ListPageImage,
    b.Breed AS Breed1, b2.Breed AS Breed2, b3.Breed AS Breed3,
    b4.Breed AS Breed4, b5.Breed AS Breed5,
    p.Price, p.StudFee,
    addr.AddressCity, addr.AddressState,
    biz.BusinessName
"""


# ── Homepage random listings ──────────────────────────────────────────────────

@router.get("/homepage-listings")
def get_homepage_listings(db: Session = Depends(get_db)):
    cached = cache_get('homepage_listings')
    if cached:
        return cached
    try:
        rows = db.execute(text("""
            SELECT TOP 30 PeopleID, Photo1, AnimalID, FullName,
                          SpeciesID, Species, Breed, Price, SalePrice
            FROM USHomePageListing
            WHERE LEN(ISNULL(CAST(PeopleID AS VARCHAR),''))>0
              AND LEN(ISNULL(Photo1,''))>0
            ORDER BY NEWID()
        """)).fetchall()
        results = []
        for r in rows:
            if len(results) >= 12:
                break
            photo = _fix_photo(r.Photo1)
            if not photo:
                continue
            results.append({
                "animal_id": r.AnimalID,
                "people_id": r.PeopleID,
                "full_name": r.FullName or '',
                "species": r.Species or '',
                "breed": r.Breed or '',
                "photo": photo,
                "price": _safe_float(getattr(r, 'Price', None)),
                "sale_price": _safe_float(getattr(r, 'SalePrice', None)),
            })
        cache_set('homepage_listings', results)
        return results
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── Filter options (breeds only for now) ─────────────────────────────────────

@router.get("/filters/{slug}")
def get_filters(slug: str, db: Session = Depends(get_db)):
    cached = cache_get(f'filters_{slug}')
    if cached:
        return cached
    try:
        sid = SLUG_TO_SPECIES_ID.get(slug)
        if not sid:
            raise HTTPException(status_code=404, detail="Species not found")
        breeds = db.execute(text("""
            SELECT BreedLookupID AS id, Breed AS name
            FROM SpeciesBreedLookupTable
            WHERE SpeciesID = :sid
              AND (breedavailable = 1 OR breedavailable IS NULL)
            ORDER BY Breed
        """), {"sid": sid}).fetchall()
        result = {
            "breeds": [{"id": r.id, "name": r.name} for r in breeds],
            "states": [],
        }
        cache_set(f'filters_{slug}', result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── For Sale listings ─────────────────────────────────────────────────────────

@router.get("/for-sale/{slug}")
def get_for_sale(
    slug: str,
    page: int = Query(1, ge=1),
    breed_id: int = Query(0),
    state_index: int = Query(0),
    min_price: float = Query(0),
    max_price: float = Query(100000000),
    ancestry: str = Query('Any'),
    sort_by: str = Query('lastupdated'),
    order_by: str = Query('desc'),
    db: Session = Depends(get_db),
):
    PER_PAGE = 10
    try:
        sid = SLUG_TO_SPECIES_ID.get(slug)
        if not sid:
            raise HTTPException(status_code=404, detail="Species not found")

        where = "WHERE a.SpeciesID=:sid AND a.PublishForSale=1 AND p.Sold=0 "
        params: dict = {"sid": sid}

        if breed_id > 0:
            where += "AND a.BreedID=:breed_id "
            params["breed_id"] = breed_id
        if state_index > 0:
            where += "AND addr.StateIndex=:state_index "
            params["state_index"] = state_index
        if min_price > 0:
            where += "AND p.Price>=:min_price "
            params["min_price"] = min_price
        if max_price < 100000000:
            where += "AND p.Price<=:max_price "
            params["max_price"] = max_price
        if ancestry in ANCESTRY_MAP:
            where += ANCESTRY_MAP[ancestry]

        order_col = {'breed': 'b.Breed', 'name': 'a.FullName', 'price': 'p.Price'}.get(sort_by.lower(), 'a.Lastupdated')
        order_dir = 'ASC' if order_by.lower() == 'asc' else 'DESC'
        offset = (page - 1) * PER_PAGE

        total = db.execute(text(f"SELECT COUNT(*) FROM Animals a {BASE_JOINS} {where}"), params).scalar() or 0

        params["offset"] = offset
        params["per_page"] = PER_PAGE
        rows = db.execute(text(f"""
            SELECT {SELECT_COLS} FROM Animals a {BASE_JOINS} {where}
            ORDER BY {order_col} {order_dir}
            OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
        """), params).fetchall()

        return {
            "total": total, "page": page, "per_page": PER_PAGE,
            "total_pages": max(1, -(-total // PER_PAGE)),
            "label": SLUG_TO_LABEL.get(slug, slug),
            "animals": [_row_to_animal(r) for r in rows],
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── Stud Services ─────────────────────────────────────────────────────────────

@router.get("/studs/{slug}")
def get_studs(
    slug: str,
    page: int = Query(1, ge=1),
    breed_id: int = Query(0),
    state_index: int = Query(0),
    min_stud_fee: float = Query(0),
    max_stud_fee: float = Query(100000000),
    percent_accoyo: str = Query('Any'),
    ancestry: str = Query('Any'),
    db: Session = Depends(get_db),
):
    PER_PAGE = 10
    try:
        sid = SLUG_TO_SPECIES_ID.get(slug)
        if not sid:
            raise HTTPException(status_code=404, detail="Species not found")

        where = "WHERE a.SpeciesID=:sid AND a.PublishStud=1 AND p.Sold=0 "
        params: dict = {"sid": sid}

        if breed_id > 0:
            where += "AND a.BreedID=:breed_id "
            params["breed_id"] = breed_id
        if state_index > 0:
            where += "AND addr.StateIndex=:state_index "
            params["state_index"] = state_index
        if min_stud_fee > 0:
            where += "AND p.StudFee>=:min_fee "
            params["min_fee"] = min_stud_fee
        if max_stud_fee < 100000000:
            where += "AND p.StudFee<=:max_fee "
            params["max_fee"] = max_stud_fee
        if percent_accoyo in ACCOYO_MAP:
            where += ACCOYO_MAP[percent_accoyo]
        if ancestry in ANCESTRY_MAP:
            where += ANCESTRY_MAP[ancestry]

        offset = (page - 1) * PER_PAGE
        total = db.execute(text(f"SELECT COUNT(*) FROM Animals a {BASE_JOINS} {where}"), params).scalar() or 0

        params["offset"] = offset
        params["per_page"] = PER_PAGE
        rows = db.execute(text(f"""
            SELECT {SELECT_COLS} FROM Animals a {BASE_JOINS} {where}
            ORDER BY a.Lastupdated DESC
            OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
        """), params).fetchall()

        return {
            "total": total, "page": page, "per_page": PER_PAGE,
            "total_pages": max(1, -(-total // PER_PAGE)),
            "label": SLUG_TO_LABEL.get(slug, slug),
            "animals": [_row_to_animal(r) for r in rows],
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))