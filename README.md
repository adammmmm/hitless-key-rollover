# Hitless Key Rollover [![CodeQL](https://github.com/adammmmm/hitless-key-rollover/actions/workflows/codeql-analysis.yml/badge.svg?branch=master)](https://github.com/adammmmm/hitless-key-rollover/actions/workflows/codeql-analysis.yml)

I got the idea when I was tasked with comparing MACsec options on Juniper/Cisco routers where Juniper's implementation of MKA (MACsec Key Agreement) didn't support time-based SAK rekeys. On low bandwidths that's fine because it'll just rekey when 4 billion packets have been secured. On higher bandwidths you're forced to use XPN (eXtended Packet Numbering) though, which in practice means no SAK rekeying unless the CKN/CAK are changed. This could be an issue in some environments where you want regular rekeys.
So, you're recommended to keep the CKN/CAK rekeys short through hitless key rollover which in turn will rekey the SAK. But since no one want to manually send out new keys every other day I created this script. 

From 20.3 and onwards, Juniper has implemented a configuration knob which should make this script obsolete for the sake of SAK-rekeying. It'll still be useful for CKN/CAK though, but that could be at a much longer interval like every 4 weeks or so. 

I've tried to fix as many bugs as possible, but I'd still do extensive testing before using it in production.

---

### Limitations

It doesn't currently support devices in different time-zones. To get that to work it would have to create different templates for each device because junos automatically sets the UTC offset in start-time to the configured system time-zone, and it isn't configurable.
So, the workaround is simply to set all devices to the same, perhaps UTC.

---

### What it does

It will create a dictionary of 31 key ids. All with maximum CKN/CAK lengths of random hex strings. The start-time will be current time plus the ROLLINTERVAL. It'll then log in to all HOSTS and show time source, the current key-chains and see if KEYCHAIN-NAME exists.

After that some checks occur that NTP is active, the active send key and receive key are the same, that there are no next keys/times in the chain and appends the active key to a list.

Then comes a check that we've got as many keys appended to the list as we have HOSTS after which we'll make sure every key is the same by making it a set instead of list.

This information is then used to create a template j2 file populated with the 31 key id dictionary where the active key will be exempted.

Eventually, it connects to all devices again and after first checking for configuration locks, commit the configuration with a comment that will let people know what's happened, if something bad happens, it does try and roll back configuration that might have already been committed to other routers.

---

### Instructions

```
git clone
pip install -r requirements.txt
```

data.yml contains a couple variables you should change:

- USER
- KEY
- ROLLINTERVAL
- KEYCHAIN-NAME
- NTP
- DEBUG
- HOSTS

USER/KEY will be the credentials for the ssh connection to the routers. ROLLINTERVAL is how often the keys will be rolled over in hours, 2 hours minimum. KEYCHAIN-NAME is:

```
[ edit security authentication-key-chains key-chain KEYCHAIN-NAME ]
```

Running keychain.py without arguments needs the routers to already be configured with at least one key in their keychain to work.

NTP is whether to exit or not if NTP is not configured on the routers. Set to False only for testing.

DEBUG should be True or False, if it's True keychain.log will have the clear-text values of every CKN/CAK.

HOSTS should be all your routers, one per line.

Add keychain.py to crontab and make it execute once every hour or so, here's an example.

```
0 * * * * /path/to/python3 /path/to/keychain.py
```

---

If you don't already have a keychain configured you can run "keychain.py init" to create one from scratch, it ignores all the checks and just creates a keychain with key 0-31. 
## DO NOT USE THE init ARGUMENT IN CRONTAB
