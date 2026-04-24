import resource

def maximize_nofile():
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    except ValueError:
        # Not root: raise soft to hard limit only
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))