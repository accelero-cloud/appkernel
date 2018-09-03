Role Based Access Management
=============================

.. warning::
    Work in progress section of documentation

* :ref:`JWT Token`
* :ref:`Setup`
* :ref:`Role based authorisation`

JWT Token
----------

Appkernel uses `JWT Token`_ for authentication and authorisation of service calls. In order to generate a Token we need a Model class which extends
the :class:`IdentityMixin` and contains an `id` and a list of `roles`, which the principal (user or api client) holds: ::

    class User(..., IdentityMixin):
        ...
        id = Property(str, required=True, generator=create_uuid_generator('U'))
        roles = Property(list, sub_type=str)

With this setup the User class will have a property, called auth_token ::

    print(('token: {}'.format(user.auth_token)))

    {
        "created": "2018-07-08T20:29:23.154563",
        "description": "test description",
        "id": "Ue92d3b52-dd8b-4f10-a496-31b342b19cc9",
        "name": "test user",
        "roles": [
            "Admin",
            "User",
            "Operator"
        ]
    }

The token is digitally signed with an RS256 algorithm.

Setup
-----

The JWT token requires a pair of private-public key-pair which can be generated using openssl in the folder {config-folder}/keys ::

    # lets create a key to sign these tokens with
    openssl genpkey -out appkernel.pem -algorithm rsa -pkeyopt rsa_keygen_bits:2048
    # lets generate a public key for it...
    openssl rsa -in appkernel.pem -out mykey.pub -pubout


Role based authorisation
------------------------
Configuring the default behaviour can be done right after registering the Model class to be exposed: ::

    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])

From now on, one needs the **Authorization** header on the requests with a valid Token containing the role `admin`. Example: ::

    'Authorization':'Bearer eyJhbGciOiJSUzI1 ... 1Mjc0MzEzNDd9.'

In case there's a custom link method on one of your Model object, the `require` parameter will contain the list of :class:`Permission`-s granting access
to the method: ::

    @action(method='POST', require=[CurrentSubject(), Role('admin')])
    def change_password(self, current_password, new_password):
        ...

Current Permissions:

- Role - a permission, which enables a user who holds the named role to access the protected resource;
- Anonymous - a static Role, which grants access to unauthenticated users;
- Denied - a static Role, which should not be given to any user; Therefore permission will be added to all resources which should not be accessed at all;
- CurrentSubject - a special purpose Permission, which allows the access of a method if the object ID and the JWT subject id is the same (can be used for users
to modify their own data);

.. _JWT Token: https://jwt.io/