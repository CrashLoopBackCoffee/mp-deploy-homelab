# Proxmox CFS compatible template

This role is a Proxmox [CFS](https://pve.proxmox.com/wiki/Proxmox_Cluster_File_System_(pmxcfs))
compatible version of the built-in `template` module.

Proxmox mounts a CFS filesystem at `/etc/pve` so any Ansible file creation modules within that
directory are likely to evebntually invoke the `atomic_move` helper function, which in turn attempts
to chmod. This is not allowed on CFS and fails.

chmod is only attempted in case the target file does not yet exist, so a currently possible
workaround is to first ensure its existence and _then_ apply the original Ansible module.

Note that the Ansible developer team states that the [current implementation behaves as
designed](https://github.com/ansible/ansible/issues/40220#issuecomment-816751221) as it assumes a
fully compliant POSIX filesystem.
