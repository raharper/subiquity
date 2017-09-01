# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from urwid import connect_signal

from subiquitycore.ui.utils import Padding
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import Form
from subiquitycore.view import BaseView

from subiquity.ui.mount import MountField
from subiquity.ui.views.filesystem.add_partition import FSTypeField


log = logging.getLogger('subiquity.ui.filesystem.add_format')


class AddFormatForm(Form):

    def __init__(self, model):
        self.model = model
        self.mountpoint_to_devpath_mapping = self.model.get_mountpoint_to_devpath_mapping()
        super().__init__()
        connect_signal(self.fstype.widget, 'select', self.select_fstype)

    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    def validate_mount(self):
        mountpoint = self.mount.value
        v = self.model.validate_mount(self.mount.value)
        if v:
            return v
        mnts = self.mountpoint_to_devpath_mapping
        dev = mnts.get(mountpoint)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, mountpoint)


class AddFormatView(BaseView):
    def __init__(self, model, controller, volume, back):
        self.model = model
        self.controller = controller
        self.volume = volume
        self.back = back

        self.form = AddFormatForm(model)
        if self.volume.fs() is not None:
            self.form.fstype.set_by_fstype(self.volume.fs().fstype)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        body = [
            Padding.line_break(""),
            self.form.as_rows(self),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons)
        ]
        format_box = Padding.center_50(ListBox(body))
        super().__init__(format_box)

    def cancel(self, button=None):
        self.back()

    def done(self, result):
        """ format spec

        {
          'format' Str(ext4|btrfs..,
          'mountpoint': Str
        }
        """
        fstype = self.form.fstype.value

        if fstype.is_mounted:
            mount = self.form.mount.value
        else:
            mount = None

        result = {
            "fstype": fstype.label,
            "mountpoint": mount,
        }
        if self.volume.fs() is not None:
            result['fstype'] = None

        log.debug("Add Format Result: {}".format(result))
        self.controller.add_format_handler(self.volume, result, self.back)
