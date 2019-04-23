# Hitless Key Rollover

This is one of my first forays into programming, so there are most likely loads of "wrong" ways of doing what I'm doing.

I got the idea when I was tasked with comparing MACsec options on juniper/cisco routers where juniper's implementation of MKA (MACsec Key Agreement) don't support time-based SAK rekeys. On low bandwidths that's fine because it'll just rekey when 4 billion packets have been secured. On higher bandwidths you're forced to use XPN (eXtended Packet Numbering) though, which in practice means no SAK rekeying unless the CKN/CAK are changed. This could be an issue in some environments where you want regular rekeys.
So, you're recommended to keep the CKN/CAK rekeys short through hitless key rollover which in turn will rekey the SAK. But since no one want to manually send out new keys every other day I created this script. 

That said, I'm assuming Juniper will implement a configuration knob which should make this script obsolete for the sake of SAK-rekeying. It'll still be useful for CKN/CAK though, but that could be at a much longer interval like every 4 weeks or so. 

---

### What it does

It will create a dictionary of 52 key ids. All with maximum CKN/CAK lengths of random hex strings. The start-time will be current time plus the ROLLINTERVAL. It'll then log in to all HOSTS and show the current key-chains and see if KEYCHAIN-NAME exists.

After that some checks occur that the active send key and receive key are the same, that there are no next keys/times in the chain and appends the active key to a list.

Then comes a check that we've got as many keys appended to the list as we have HOSTS after which we'll make sure every key is the same by making it a set instead of list.

This information allows us to create the template jinja2 file populated with the 52 key id dict where the active key will be exempted.

Eventually, we connect to all devices again and commit the configuration with a comment that will let people know what's happened.

---

### Instructions

data.yml contains a couple variables you should change:

- USER
- PASS
- ROLLINTERVAL
- KEYCHAIN-NAME
- LOGGING
- HOSTS

Guessing they should be pretty self explanatory, USER/PASS will be the credentials for the ssh connection to the routers. ROLLINTERVAL is how often the keys will be rolled over in hours, 2 hours minimum. KEYCHAIN-NAME is:

[ edit security authentication-key-chains key-chain **THIS** ]

keychain.py currently needs to already be configured with at least one key to work.

If you don't already have a keychain configured you can run init.py to create one from scratch, it ignores all the checks and just configures a keychain with key 0-51. 
LOGGING should be **True** or **False**, if it's True keychain.log will have the clear-text values of every CKN/CAK value.

And of course HOSTS should be all your routers ip-addresses.

Add keychain.py to crontab and make it execute once every ROLLINTERVAL/2, that way there will at most be half a ROLLINTERVAL drift. **DO NOT USE INIT.PY IN CRON**
