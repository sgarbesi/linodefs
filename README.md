## Install

```
./setup.py install --user
```

map linode api entities to a fuse filesystem.

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
				
