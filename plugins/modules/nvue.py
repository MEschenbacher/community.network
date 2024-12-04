#!/usr/bin/python
# -*- coding: utf-8 -*-

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = '''
---
module: nvue
author: "Maximilian Eschenbacher (ERNW Enno Rey Netzwerke GmbH)"
short_description: Configure cumulus linux using nvue
description:
options:
    apply:
        description:
            - When true, performs a 'nv config apply' at the end of the block.
              Mutually exclusive with I(atomic).
        default: false
        type: bool
    atomic:
        description:
            - When true, equivalent to I(detach) and I(apply) being true.
              Mutually exclusive with I(detach) and I(apply).
        default: false
        type: bool
    commands:
        description:
            - A list of strings containing the nv commands to run. Mutually
              exclusive with I(template).
    confirm:
        description:
            - If I(apply)ing a configuration, this option sets up the confirm mechanism of
              nvue with a I(confirm_timeout) (default 10m). Implies I(apply=true).
        type: bool
    confirm_no:
        description:
            - Execute confirm no to deny the configuration and immediately rollback the
              configuration.
        type: bool
    confirm_timeout:
        description:
            - Set the timeout after a pending confirm automatically rolls back the previous
              configuration. Supported suffixes m (minute), s (second), h (hour). Examples:
              10m or 30s or 1h.
        type: str
    confirm_yes:
        description:
            - Execute confirm yes to confirm the configuration and stop the rollback.
        type: bool
    detach:
        description:
            - Boolean. When true, perform a 'nv config detach' before the block.
              This cleans out any uncommitted changes in the buffer.
              Mutually exclusive with I(atomic).
        default: false
        type: bool
    save:
        description:
            - When true, performs a 'nv config save' at the end of the block.
        default: false
        type: bool
    template:
        description:
            - A single, multi-line string with jinja2 formatting. This string
              will be broken by lines, and each line will be run through nv.
              Mutually exclusive with I(commands).
notes:
    - Supports check_mode. Note that when using check_mode, I(detach) is always true, I(apply)
      and I(save) is always false.
'''

EXAMPLES = '''

- name: Add two interfaces without committing any changes
  community.network.nvue:
    commands:
        - set interface swp1
        - set interface swp2

- name: Modify hostname and commit the change
  community.network.nvue:
    commands:
      - set platform hostname value cumulus-1
    apply: true

- name: Add 48 interfaces and apply
  community.network.nvue:
    template: |
      {% for num in range(1,49) %}
      set interface swp{{num}}
      {% endfor %}
    apply: true

- name: Fetch Status Of Interface
  community.network.nvue:
    commands:
      - show interface swp1
  register: output

- name: Print Status Of Interface
  ansible.builtin.debug:
    var: output
'''

RETURN = '''
changed:
    description: whether the configuration was changed
    returned: changed
    type: bool
    sample: True
msg:
    description: human-readable report of success or failure
    returned: always
    type: str
    sample: "interface bond0 config updated"
'''

from ansible.module_utils.basic import AnsibleModule


def command_helper(module, command):
    """
    Run a command and return stdout but hard fail on error conditions.
    """
    exitstatus, stdout, stderr = module.run_command("/usr/bin/nv %s" % command)
    if exitstatus != 0:
        module.fail_json(msg=dict(msg="Failed on line '%s'" % (command,), rc=exitstatus, stdout=stdout, stderr=stderr))
    return str(stdout).strip()

def commands_helper(module, commands):
    """
    Run a list of commands.
    """
    for line in commands:
        line = line.strip()
        if line == "":
            continue
        yield command_helper(module, line)

def check_pending(module):
    return command_helper(module, "config diff")

def run_nvue(module):
    commands = module.params.get('commands')
    if not commands:
        commands = module.params.get('template').splitlines()
    do_apply = module.params.get('apply')
    apply_options = ''
    do_detach = module.params.get('detach')
    do_save = module.params.get('save')
    do_confirm = module.params.get('confirm')
    do_confirm_no = module.params.get('confirm_no')
    confirm_timeout = module.params.get('confirm_timeout')
    do_confirm_yes = module.params.get('confirm_yes')
    if do_confirm:
        do_apply = True
        apply_options += ' --confirm ' + confirm_timeout
    if do_confirm_yes:
        apply_options += ' --confirm-yes'
    if do_confirm_no:
        apply_options += ' --confirm-no'

    changed = False

    if module.params.get('atomic'):
        do_apply = True
        do_detach = True

    if do_detach or module.check_mode:
        command_helper(module, "config detach")

    before = check_pending(module)
    output = list(commands_helper(module, commands))
    after = check_pending(module)

    changed = before != after

    # changed is not a valid indicator for checking if the config needs application
    # instead we use after to see if there is pending config
    if after and do_apply and not module.check_mode:
        changed = True
        ret = command_helper(module, "config apply --assume-yes " + apply_options)
        if ret:
            output.append(ret)

    if do_save and not module.check_mode:
        changed = True
        ret = command_helper(module, "config save")
        if ret:
            output.append(ret)

    return changed, dict(before=before, after=after), output

def main():
    module = AnsibleModule(argument_spec=dict(
            apply=dict(required=False, type='bool', default=False),
            atomic=dict(required=False, type='bool', default=False),
            commands=dict(required=False, type='list', default=[]),
            confirm=dict(required=False, type='bool', default=False),
            confirm_no=dict(required=False, type='bool', default=False),
            confirm_timeout=dict(required=False, type='str', default='10m'),
            confirm_yes=dict(required=False, type='bool', default=False),
            detach=dict(required=False, type='bool', default=False),
            save=dict(required=False, type='bool', default=False),
            template=dict(required=False, type='str')
        ),
        supports_check_mode=True,
        mutually_exclusive=[
            ('commands', 'template'),
            ('apply', 'atomic'),
            ('confirm', 'atomic'),
            ('confirm_no', 'atomic'),
            ('confirm_yes', 'atomic'),
            ('confirm_no', 'confirm_yes'),
            ('confirm', 'confirm_yes'),
            ('confirm', 'confirm_no'),
            ('detach', 'atomic'),
        ],
    )

    changed, diff, output = run_nvue(module)

    module.exit_json(changed=changed, diff=diff, msg=output)

if __name__ == '__main__':
    main()
