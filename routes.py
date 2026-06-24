import pandas as pd
from flask import request, render_template
from models import Person

ALLOWED_EXTENSIONS = {"csv"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_csv_file(file_storage):
    """
    Parse uploaded CSV directly from memory without saving to disk.
    Returns list of dictionaries (one dict per row).
    """
    file_storage.stream.seek(0)
    df = pd.read_csv(file_storage)

    # Replace NaN with None for cleaner downstream processing
    df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")


def register_routes(app, db):

    @app.route('/', methods=['GET'])
    def home():
        return render_template('index.html')

    @app.route('/upload', methods=['GET'])
    def upload():
        return render_template('upload.html')

    @app.route('/upload-trades', methods=['POST'])
    def upload_file():
        """
        Parse one or many uploaded CSV files directly in memory.
        No file is saved to disk.
        No flash/session usage.
        """
        file_label = request.form.get('file_label', '').strip()
        files = request.files.getlist("files")

        print("DEBUG request.files:", request.files)
        print("DEBUG files received:", [f.filename for f in files if f and f.filename])

        if not files or all(f.filename == '' for f in files):
            return render_template(
                "upload.html",
                error_message="Please select at least one CSV file.",
                file_label=file_label
            )

        parsed_payload = []
        total_rows = 0

        try:
            for file in files:
                if not file or file.filename == '':
                    continue

                if not allowed_file(file.filename):
                    return render_template(
                        "upload.html",
                        error_message=f'"{file.filename}" is not a CSV file.',
                        file_label=file_label
                    )

                rows = parse_csv_file(file)

                parsed_payload.append({
                    "source_file": file.filename,
                    "row_count": len(rows),
                    "rows": rows[:5]   # preview first 5 rows only
                })

                total_rows += len(rows)

            return render_template(
                "upload.html",
                success_message=f"Successfully parsed {len(parsed_payload)} CSV file(s) with {total_rows} total row(s).",
                parsed_payload=parsed_payload,
                total_rows=total_rows,
                file_label=file_label
            )

        except Exception as err:
            print("CSV parsing error:", err)
            return render_template(
                "upload.html",
                error_message=f"CSV parsing failed: {str(err)}",
                file_label=file_label
            )

    @app.route('/pyramiding', methods=['GET'])
    def pyramiding():
        return render_template('index.html')

    @app.route('/dashboard', methods=['GET'])
    def dashboard():
        return render_template('index.html')

    @app.route('/people', methods=['GET', 'POST'])
    def people():
        if request.method == 'GET':
            people = Person.query.all()
            return render_template('index.html', people=people)

        elif request.method == 'POST':
            name = request.form.get('name')
            age = int(request.form.get('age'))
            job = request.form.get('job')

            person = Person(name=name, age=age, job=job)
            db.session.add(person)
            db.session.commit()

            people = Person.query.all()
            return render_template('index.html', people=people)

    @app.route('/delete/<pid>', methods=['DELETE'])
    def delete(pid):
        Person.query.filter(Person.pid == pid).delete()
        db.session.commit()
        people = Person.query.all()
        return render_template('index.html', people=people)