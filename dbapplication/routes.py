from flask import render_template,request
from models import Person

def register_routes(app,db):

    @app.route('/',methods = ['GET'])
    def home():
         return render_template('index.html')
     
    @app.route('/upload',methods = ['GET'])
    def upload():
         return render_template('upload.html')
     
    @app.route('/pyramiding',methods = ['GET'])
    def pyramiding():
         return render_template('index.html')
    
    @app.route('/dashboard',methods = ['GET'])
    def dashboard():
         return render_template('index.html')

    @app.route('/people',methods = ['GET','POST'])
    def people():
        if request.method == 'GET':
            people = Person.query.all()
            # return str(people)
            return render_template('index.html',people = people)

        elif request.method == 'POST':
            name = request.form.get('name')
            age = int(request.form.get('age'))
            job = request.form.get('job')  

            #creating the new object
            person = Person(name = name, age=age, job=job)
            db.session.add(person)
            db.session.commit()

            people = Person.query.all()
            # return str(people)
            return render_template('index.html',people = people)

    @app.route('/delete/<pid>',methods = ['DELETE'])    
    def delete(pid):
        Person.query.filter(Person.pid == pid).delete()
        db.session.commit()
        people = Person.query.all()
            # return str(people)
        return render_template('index.html',people = people)

        