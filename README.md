# Hitless Key Rollover

This is one of my first forays into programming, so there are most likely loads of "wrong" ways of doing what I'm doing.

I got the idea when comparing macsec options on juniper/cisco routers where juniper don't have time-based SAK rekeys. The official recommendation is instead to keep the CKN/CAK rekeys short through hitless key rollover which in turn will rekey the SAK. But since no one want to manually send out new keys every other day I created this script. 

---

### What it does

It will create a dictionary of 64 key ids. All with maximum CKN+CAK lengths of random hex strings. The start-time will be current time plus the ROLLINTERVAL. It'll then log in to all HOSTS and show the current key-chains and see if KEYCHAIN-NAME exists.

After that some checks occur that the active send key and receive key are the same, that there are no next keys/times in the chain and appends the active key to a list.

Then comes a check that we've got as many keys appended to the list as we have HOSTS after which we'll make sure every key is the same by making it a set instead of list.

This information allows us to create the template jinja2 file populated with the 64 key id dict where the active key will be exempted.

Eventually, we connect to all devices again and commit the configuration with a comment that will let people know what's happened.

---

### Instructions

data.yml contains a couple variables you should change:

- USER

- PASS

- ROLLINTERVAL

- KEYCHAIN-NAME

- HOSTS

Guessing they should be pretty self explanatory, USER/PASS will be the credentials for the ssh connection to the routers. ROLLINTERVAL is how often the keys will be rolled over in hours. KEYCHAIN-NAME is:

[ edit security authentication-key-chains key-chain **THIS** ]

It currently needs to already be configured with one key for the script to work.

And of course HOSTS should be all your routers ip-addresses.

Add this to crontab and make it execute once every ROLLINTERVAL/2.
