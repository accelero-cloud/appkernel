Preparing translation for your services
=======================================

Writing code which will be translated using babel
-------------------------------------------------

Strings which need to be translated should be marked with the babel specific translation marker function (eg. _('username')). ::

    from flask_babel import _

    def some_function():
        raise ServiceException(403, _('Current password is not correct'))

This method will work within the request context, however when you need to work outside of that context you might need to use the ``lazy_gettext`` function: ::

    from flask_babel import lazy_gettext as _l

    class LoginForm(FlaskForm):
        username = StringField(_l('Username'), validators=[DataRequired()])


Preparation
-----------
You need to add a small configuration file, called *babel.cfg* to the root folder of your project: ::

    [python: **.py]
    [jinja2: app/templates/**.html]
    extensions=jinja2.ext.autoescape,jinja2.ext.with_

**Mind the path definition in the configuration file for the python and jinja file.**
The first two lines define the filename patterns for Python and Jinja2 template files respectively.
The third line defines two extensions provided by the Jinja2 template engine that help Flask-Babel properly parse template files.


Generating the translation files
--------------------------------
To extract all the texts to the .pot file, you can use the following command (make sure that your're switched to your virtual environment): ::

    (venv) $ pybabel extract -F babel.cfg -k _l -o messages.pot .
    (venv) $ pybabel init -i messages.pot -d ./translations -l en
    (venv) $ pybabel compile -d ./translations
The first comamnd will create a list of key-strings in the local directory and write it into a messages.pot file. In our case it will search for strings
marked with the babel specific _()

Updating the translation files
------------------------------

Once you add new text to your source-files, you can re-generate the translation source files with the following commands ::

    (venv) $ pybabel extract -F babel.cfg -k _l -o messages.pot .
    (venv) $ pybabel update -i messages.pot -d ./translations
    (venv) $ pybabel compile -d ./translations
