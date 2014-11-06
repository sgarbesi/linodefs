## Purpose
Maps linode api entities to a fuse filesystem.

## Install

```
./setup.py install --user
 mkdir mnt
 read LINODE_API_KEY

 # I rerun this line after each change to linodefs.py
 # .. and hoping each time that this leap will be the leap home.
 (sudo umount mnt; ./linodefs.py -o api_key=$LINODE_API_KEY mnt; cd mnt; ls)

```




### Design
Maybe it will look like this?
```
/mnt/lnfs/linodes/
                  linode1234
		  happy -> linode1234
		           /
			    disks
			    configs/
			            config123
				             disks
			    bin/
			        reboot
				shutdown
				start
				destroy
```
It does not look that yet so far.. Very subject to change.
