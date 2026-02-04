from fastapi import FastAPI, HTTPException, Query, Body, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
import os
from math import ceil
import shutil

app = FastAPI()

BASE_DIR = 'D:\\Praveen\\Project\\'
#BASE_DIR = os.path.dirname(os.path.abspath(_file_))
DATA_DIR = os.path.join(BASE_DIR, "data")

STATIC_DIR = os.path.join(BASE_DIR, "static")
PHOTO_ROOT = os.path.join(STATIC_DIR, "photos")

os.makedirs(PHOTO_ROOT, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PAGE_SIZE = 15


# -----------------------------
# Helpers
# -----------------------------

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def normalize_row(row: dict):
    return {
        "sno": row.get("sno") or row.get("SNo"),
        "name": row.get("name") or row.get("Name"),
        "father/husband": row.get("father/husband") or row.get("F_H_Name"),
        "age": row.get("age") or row.get("Age"),
        "sex": row.get("sex") or row.get("Sex"),
        "addr": row.get("addr") or row.get("Addr"),
        "epic": row.get("epic") or row.get("EPIC"),
        "mobile": row.get("mobile", ""),
        "photo": row.get("photo", ""),
    }


def list_json_files():
    return sorted(
        f for f in os.listdir(DATA_DIR)
        if f.endswith(".json") and os.path.isfile(os.path.join(DATA_DIR, f))
    )


def json_name_no_ext(filename: str):
    return os.path.splitext(filename)[0]


def photo_folder_for_json(filename: str):
    folder = os.path.join(PHOTO_ROOT, json_name_no_ext(filename))
    os.makedirs(folder, exist_ok=True)
    return folder


def load_data(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="JSON file not found")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = list(raw.values())[0]

    return [normalize_row(r) for r in raw]


def save_data(filename: str, data):
    path = os.path.join(DATA_DIR, filename)

    # merge back into original structure
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    wrapped = isinstance(raw, dict)

    if wrapped:
        key = list(raw.keys())[0]
        raw[key] = data
    else:
        raw = data

    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)


# -----------------------------
# AJAX update mobile
# -----------------------------

@app.post("/update-mobile")
def update_mobile(payload: dict = Body(...)):
    filename = payload.get("filename")
    sno = payload.get("sno")
    mobile = payload.get("mobile")

    data = load_data(filename)

    for row in data:
        if int(row.get("sno")) == int(sno):
            row["mobile"] = mobile
            save_data(filename, data)
            return {"status": "success"}

    raise HTTPException(status_code=404, detail="Record not found")


# -----------------------------
# Upload / change photo
# -----------------------------

@app.post("/upload-photo")
async def upload_photo(
    filename: str = Query(...),
    sno: int = Query(...),
    photo: UploadFile = File(...)
):

    ext = os.path.splitext(photo.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Only JPG/PNG allowed")

    folder = photo_folder_for_json(filename)

    new_name = f"{sno}{ext}"
    save_path = os.path.join(folder, new_name)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    data = load_data(filename)

    for row in data:
        if int(row.get("sno")) == sno:
            row["photo"] = new_name
            save_data(filename, data)
            return {"status": "success", "photo": new_name}

    raise HTTPException(status_code=404, detail="Record not found")


# -----------------------------
# Main page
# -----------------------------

@app.get("/table", response_class=HTMLResponse)
def voters_table(
    file: str | None = None,
    page: int = 1,

    name: str | None = None,
    age_op: str | None = None,
    age_val: str | None = None,
    sex: str | None = None,
    addr: str | None = None,
):

    files = list_json_files()
    if not files:
        return "<h2>No JSON files found</h2>"

    if not file:
        file = files[0]

    data = load_data(file)

    sexes = sorted({r.get("sex") for r in data if r.get("sex")})
    addrs = sorted({r.get("addr") for r in data if r.get("addr")})

    # -----------------------------
    # Filtering
    # -----------------------------

    filtered = []
    for row in data:
        match = True

        if name and name.lower() not in str(row.get("name", "")).lower():
            match = False

        if sex and sex.lower() != str(row.get("sex", "")).lower():
            match = False

        if addr and addr.lower() != str(row.get("addr", "")).lower():
            match = False

        if age_op and age_val:
            age_filter_val = safe_int(age_val)
            age = safe_int(row.get("age"))

            if age_op == "gt" and age <= age_filter_val:
                match = False
            if age_op == "lt" and age >= age_filter_val:
                match = False
            if age_op == "eq" and age != age_filter_val:
                match = False

        if match:
            filtered.append(row)

    # -----------------------------
    # Dashboard stats
    # -----------------------------

    total_records = len(filtered)

    male_count = sum(1 for r in filtered if str(r.get("sex")).lower() == "m")
    female_count = sum(1 for r in filtered if str(r.get("sex")).lower() == "f")

    below_30 = sum(1 for r in filtered if safe_int(r.get("age")) < 30)
    between_30_50 = sum(1 for r in filtered if 30 <= safe_int(r.get("age")) <= 50)
    above_50 = sum(1 for r in filtered if safe_int(r.get("age")) > 50)

    unique_addrs = len({r.get("addr") for r in filtered if r.get("addr")})

    mobile_filled = sum(1 for r in filtered if r.get("mobile"))
    mobile_pct = round((mobile_filled / total_records * 100), 1) if total_records else 0

    # -----------------------------
    # Pagination
    # -----------------------------

    total_pages = max(1, ceil(total_records / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_data = filtered[start:end]

    def page_link(p):
        params = {
            "file": file,
            "page": p,
            "name": name or "",
            "sex": sex or "",
            "addr": addr or "",
            "age_op": age_op or "",
            "age_val": age_val or "",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items() if v != "")
        return f"/table?{query}"

    window = 3
    start_page = max(1, page - window)
    end_page = min(total_pages, page + window)

    page_numbers_html = ""
    for p in range(start_page, end_page + 1):
        if p == page:
            page_numbers_html += f"<b style='padding:4px'>{p}</b>"
        else:
            page_numbers_html += f"<a href='{page_link(p)}' style='padding:4px'>{p}</a>"

    json_folder = json_name_no_ext(file)

    # -----------------------------
    # HTML
    # -----------------------------

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial; margin: 40px; }}

            .dashboard {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 15px;
                margin-bottom: 25px;
            }}

            .card {{
                background: #f8f9fa;
                border: 1px solid #ddd;
                padding: 15px;
                border-radius: 6px;
                text-align: center;
            }}

            input, select {{ padding: 6px; margin: 4px; }}

            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #333; padding: 8px; }}
            th {{ background: #f2f2f2; }}

            .status {{ font-size: 12px; color: green; }}

            .thumb-wrapper {{ position: relative; display: inline-block; }}
            img.thumb {{ width: 40px; height: 55px; object-fit: cover; border: 1px solid #999; }}

            .hover-preview {{
                display: none;
                position: absolute;
                top: -10px;
                left: 50px;
                background: white;
                border: 1px solid #333;
                padding: 6px;
                z-index: 999;
            }}

            .hover-preview img {{ height: 200px; }}

            .thumb-wrapper:hover .hover-preview {{ display: block; }}
        </style>
    </head>

    <body>

        <h2>Voter Dashboard</h2>

        <div class="dashboard">
            <div class="card"><b>{total_records}</b><br>Total</div>
            <div class="card"><b>{male_count}</b><br>Male</div>
            <div class="card"><b>{female_count}</b><br>Female</div>
            <div class="card"><b>{below_30}</b><br>&lt;30</div>
            <div class="card"><b>{between_30_50}</b><br>30–50</div>
            <div class="card"><b>{above_50}</b><br>&gt;50</div>
            <div class="card"><b>{unique_addrs}</b><br>Areas</div>
            <div class="card"><b>{mobile_pct}%</b><br>Mobile</div>
        </div>

        <!-- FILE SELECT -->
        <form method="get">
            <b>Select JSON:</b>
            <select name="file" onchange="this.form.submit()">
                {''.join(
                    f'<option value="{f}" {"selected" if f==file else ""}>{f}</option>'
                    for f in files
                )}
            </select>
        </form>

        <hr>

        <!-- FILTER FORM -->
        <form method="get">
            <input type="hidden" name="file" value="{file}">

            <input name="name" placeholder="Name" value="{name or ''}">

            <select name="age_op">
                <option value="">Age</option>
                <option value="gt" {"selected" if age_op=="gt" else ""}>Greater</option>
                <option value="lt" {"selected" if age_op=="lt" else ""}>Less</option>
                <option value="eq" {"selected" if age_op=="eq" else ""}>Equal</option>
            </select>

            <input type="number" name="age_val" value="{age_val or ''}" placeholder="Age">

            <select name="sex">
                <option value="">All Sex</option>
                {''.join(f'<option value="{s}" {"selected" if s==sex else ""}>{s}</option>' for s in sexes)}
            </select>

            <select name="addr">
                <option value="">All Address</option>
                {''.join(f'<option value="{a}" {"selected" if a==addr else ""}>{a}</option>' for a in addrs)}
            </select>

            <button type="submit">Filter</button>
        </form>

        <br>

        <table>
            <tr>
                <th>S.No</th>
                <th>Name</th>
                <th>Father/Husband</th>
                <th>Age</th>
                <th>Sex</th>
                <th>Address</th>
                <th>EPIC</th>
                <th>Mobile</th>
                <th>Photo</th>
                <th>Save</th>
            </tr>
    """

    for row in page_data:
        photo_html = (
            f'''
            <div class="thumb-wrapper">
                <img class="thumb" src="/static/photos/{json_folder}/{row["photo"]}">
                <div class="hover-preview">
                    <img src="/static/photos/{json_folder}/{row["photo"]}">
                </div>
            </div>
            '''
            if row.get("photo")
            else "No Photo"
        )

        html += f"""
        <tr>
            <td>{row.get("sno")}</td>
            <td>{row.get("name")}</td>
            <td>{row.get("father/husband")}</td>
            <td>{row.get("age")}</td>
            <td>{row.get("sex")}</td>
            <td>{row.get("addr")}</td>
            <td>{row.get("epic")}</td>

            <td><input id="mobile-{row['sno']}" value="{row.get('mobile','')}" size="12"></td>

            <td>{photo_html}</td>

            <td>
                <button onclick="saveMobile('{file}', {row['sno']})">Save</button>
                <span class="status" id="status-{row['sno']}"></span>
            </td>
        </tr>
        """

    html += f"""
        </table>

        <br>

        <div style="font-size:14px;">
            {"<a href='"+page_link(1)+"'>First</a> | " if page>1 else ""}
            {"<a href='"+page_link(page-1)+"'>Prev</a> | " if page>1 else ""}

            {page_numbers_html}

            {" | <a href='"+page_link(page+1)+"'>Next</a>" if page<total_pages else ""}
            {" | <a href='"+page_link(total_pages)+"'>Last</a>" if page<total_pages else ""}
        </div>

        <script>
        function saveMobile(file, sno) {{
            const mobile = document.getElementById("mobile-" + sno).value;

            fetch("/update-mobile", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{
                    filename: file,
                    sno: sno,
                    mobile: mobile
                }})
            }})
            .then(() => {{
                document.getElementById("status-" + sno).innerText = "Saved ✔";
            }})
            .catch(() => {{
                document.getElementById("status-" + sno).innerText = "Error ❌";
            }});
        }}
        </script>

    </body>
    </html>
    """

    return html