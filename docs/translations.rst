I18n (Internationalisation)
===========================

.. warning::
    Work in progress section of documentation

The translation support of appkernel is built on `babel`_ and `flask-babel`_.

.. _babel: http://babel.pocoo.org/en/latest/
.. _flask-babel: https://pythonhosted.org/Flask-Babel/

Strings which need to be internationalized should be marked with the babel specific '_' (underscore) marker function (eg. _('username')). ::

    from flask_babel import _

    def some_function():
        raise ServiceException(403, _('Current password is not correct'))

This method will work within the request context of flask, however when in need to work outside the request context we might need to use the ``lazy_gettext`` function: ::

    from flask_babel import lazy_gettext as _l

    class LoginForm(FlaskForm):
        username = StringField(_l('Username'), validators=[DataRequired()])

One can also add notes to the messages, which will be extracted into the translation files, helping the translator with context information. ::

    # NOTE: This is a comment about `Foo Bar`
    _('Foo Bar')

Preparation
-----------
You need to add a small configuration file, called *babel.cfg* to the root folder of your project: ::

    [model_messages: **.py]
    extract_messages = _l

    ;[python: **.py]
    ;extract_messages = _l

    [jinja2: app/templates/**.html]
    extensions=jinja2.ext.autoescape,jinja2.ext.with_\

The first two lines define the filename patterns for Python. We won't use the built-in python extractor because that is not reading the ``Parameter`` classes.

The third section defines two extensions provided by the Jinja2 template engine that help Flask-Babel properly parse template files.
**Mind the path definition in the configuration file for the python and jinja file.**

Generating the translation files
--------------------------------
To extract all the texts to the .pot file, you can use the following command (make sure that your're switched to your virtual environment): ::

    (venv) $ pybabel extract -F babel.cfg -k _l -o messages.pot .
    (venv) $ pybabel init -i messages.pot -d ./translations -l en
    (venv) $ pybabel init -i messages.pot -d ./translations -l de
    (venv) $ pybabel compile -d ./translations
The first command will create a list of key-strings in the local directory and write it into a messages.pot file. In our case it will search for strings
marked with the babel specific _() function.
The second and third command will copy the keys from the messages.pot into a folder called `en` and `de` inside of the folder translations. This is where
the actual actual translation should take place. Once you're ready with the localisation, you are good to execute the *compile* command.

We need one more step, namely to add the supported languages to our configuration: ::

    appkernel:
        i18n:
        languages: ['en-US','de-DE']

Updating the translation files
------------------------------
Once you add new text to your source-files, you can re-generate the translation source files with the following commands ::

    (venv) $ pybabel extract -F babel.cfg -k _l -o messages.pot .
    (venv) $ pybabel update -i messages.pot -d ./translations
    (venv) $ pybabel compile -d ./translations

One can also use the ::

    python ./setup.py compile_catalog --help


