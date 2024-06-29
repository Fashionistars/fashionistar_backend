import os
from rave_python import Rave
print("Lol")
rave = Rave(publicKey="FLWPUBK_TEST-c842b7e99eac75a0c758a4f48fd772e3-X", secretKey="FLWSECK_TEST-4ae0af268a7e86d4014333e7e6a72d78-X", usingEnv=False)
# Subsequqent calls will automatically have the header added
response = rave.Transfer.bvnResolve("123456789")
print(response)

