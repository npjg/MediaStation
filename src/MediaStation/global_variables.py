
# Holds a reference to the Application, which is currently 
# necessary for contexts to execute an application-wide 
# search for assets (for instance, for INSTALL.CXT to find
# asset headers in another context).
application = None

# Technically the version could be accessed from the application,
# but this reduces some of the complexity there by storing a 
# reference directly.
version = None
