Role Based Access Management
=============================

.. warning::
    Work in progress section of documentation

Generating the encryption keys
------------------------------

The keys can be generated using openssl in the folder {config-folder}/keys ::

    # lets create a key to sign these tokens with
    openssl genpkey -out appkernel.pem -algorithm rsa -pkeyopt rsa_keygen_bits:2048
    # lets generate a public key for it...
    openssl rsa -in appkernel.pem -out mykey.pub -pubout
