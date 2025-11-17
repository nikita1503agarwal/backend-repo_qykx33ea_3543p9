import os
from datetime import date, datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import CheckIn, Goal, Reflection

app = FastAPI(title="PERMA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------- Helpers -------

def to_str_id(doc: dict):
    if not doc:
        return doc
    d = dict(doc)
    if d.get("_id"):
        d["id"] = str(d.pop("_id"))
    return d


def get_user_id(header_val: Optional[str]) -> str:
    return header_val or "anon"


# ------- Health/Test -------
@app.get("/")
def read_root():
    return {"message": "PERMA backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ------- Check-ins -------
@app.post("/checkins")
def create_checkin(payload: CheckIn, x_user_id: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    data = payload.model_dump()
    data["user_id"] = data.get("user_id") or user_id
    # Upsert: one check-in per user per date
    col = db["checkin"]
    existing = col.find_one({"user_id": data["user_id"], "date": data["date"]})
    if existing:
        col.update_one({"_id": existing["_id"]}, {"$set": {**data, "updated_at": datetime.utcnow()}})
        updated = col.find_one({"_id": existing["_id"]})
        return to_str_id(updated)
    _id = create_document("checkin", data)
    created = col.find_one({"_id": ObjectId(_id)})
    return to_str_id(created)


@app.get("/checkins")
def list_checkins(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(30, ge=1, le=365),
    x_user_id: Optional[str] = None,
):
    user_id = get_user_id(x_user_id)
    flt: dict = {"user_id": user_id}
    if start or end:
        rng = {}
        if start:
            rng["$gte"] = start
        if end:
            rng["$lte"] = end
        flt["date"] = rng
    docs = db["checkin"].find(flt).sort("date", 1).limit(limit)
    return [to_str_id(d) for d in docs]


@app.get("/stats/summary")
def stats_summary(
    days: int = Query(30, ge=1, le=365),
    x_user_id: Optional[str] = None,
):
    user_id = get_user_id(x_user_id)
    # Fetch last N days
    docs = list(db["checkin"].find({"user_id": user_id}).sort("date", -1).limit(days))
    if not docs:
        return {
            "count": 0,
            "avg": {"p": None, "e": None, "r": None, "m": None, "a": None},
            "latest": None,
            "streak": 0,
        }
    # Averages
    keys = ["p", "e", "r", "m", "a"]
    sums = {k: 0 for k in keys}
    for d in docs:
        for k in keys:
            sums[k] += int(d.get(k, 0))
    n = len(docs)
    avgs = {k: round(sums[k] / n, 2) for k in keys}
    latest = to_str_id(docs[0])
    # Streak: consecutive days with any check-in ending today
    def parse(dstr):
        return datetime.fromisoformat(dstr).date()
    today = date.today()
    unique_dates = sorted({parse(d["date"]) for d in docs}, reverse=True)
    streak = 0
    expected = today
    for dday in unique_dates:
        if dday == expected:
            streak += 1
            expected = expected.fromordinal(expected.toordinal() - 1)
        else:
            break
    return {"count": n, "avg": avgs, "latest": latest, "streak": streak}


# ------- Goals -------
class GoalPatch(BaseModel):
    title: Optional[str] = None
    dimension: Optional[str] = None
    cadence: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None


@app.post("/goals")
def create_goal(payload: Goal, x_user_id: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    data = payload.model_dump()
    data["user_id"] = data.get("user_id") or user_id
    _id = create_document("goal", data)
    doc = db["goal"].find_one({"_id": ObjectId(_id)})
    return to_str_id(doc)


@app.get("/goals")
def list_goals(x_user_id: Optional[str] = None, status: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    flt = {"user_id": user_id}
    if status:
        flt["status"] = status
    docs = db["goal"].find(flt).sort("created_at", -1)
    return [to_str_id(d) for d in docs]


@app.patch("/goals/{goal_id}")
def update_goal(goal_id: str, payload: GoalPatch, x_user_id: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    try:
        oid = ObjectId(goal_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid goal id")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    res = db["goal"].update_one({"_id": oid, "user_id": user_id}, {"$set": {**updates, "updated_at": datetime.utcnow()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    doc = db["goal"].find_one({"_id": oid})
    return to_str_id(doc)


@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: str, x_user_id: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    try:
        oid = ObjectId(goal_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid goal id")
    res = db["goal"].delete_one({"_id": oid, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


# ------- Reflections -------
@app.post("/reflections")
def create_reflection(payload: Reflection, x_user_id: Optional[str] = None):
    user_id = get_user_id(x_user_id)
    data = payload.model_dump()
    data["user_id"] = data.get("user_id") or user_id
    _id = create_document("reflection", data)
    doc = db["reflection"].find_one({"_id": ObjectId(_id)})
    return to_str_id(doc)


@app.get("/reflections")
def list_reflections(x_user_id: Optional[str] = None, tag: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    user_id = get_user_id(x_user_id)
    flt = {"user_id": user_id}
    if tag:
        flt["tags"] = tag
    docs = db["reflection"].find(flt).sort("created_at", -1).limit(limit)
    return [to_str_id(d) for d in docs]


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
