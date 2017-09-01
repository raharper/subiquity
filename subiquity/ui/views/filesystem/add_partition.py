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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging
from urwid import connect_signal, Text

from subiquitycore.ui.buttons import PlainButton
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import (
    Form,
    FormField,
    IntegerField,
    StringField,
    )
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import Selector
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    humanize_size,
    dehumanize_size,
    HUMAN_UNITS,
    )
from subiquity.ui.mount import MountField


log = logging.getLogger('subiquity.ui.filesystem.add_partition')


class FSTypeField(FormField):
    def _make_widget(self, form):
        return Selector(opts=form.supported_filesystems)


class PartitionFormatForm(Form):

    def __init__(self, supported_filesystems, size_limit, mountpoint_to_devpath_mapping):
        self.supported_filesystems = supported_filesystems
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        super().__init__()
        self.size_limit = size_limit
        if size_limit is not None:
            self.size_str = humanize_size(size_limit)
            self.size.caption = "Size (max {})".format(self.size_str)
        else:
            self.remove_field('partnum')
            self.remove_field('size')
        connect_signal(self.fstype.widget, 'select', self.select_fstype)

    def initialize_from_object(self, volume):
        mount = None
        fs = volume.fs()
        if fs is not None:
            mount = fs.mount()
        if volume.type == 'partition':
            self.partnum.value = volume.number
            self.size.value = humanize_size(volume.size)
        if fs is not None:
            sel = self.fstype.widget.selection_by_label(fs.fstype)
            self.fstype.value = sel.value
            if sel.value.is_mounted and mount is not None:
                self.mount.value = mount.path

    def result(self):

        fstype = self.fstype.value

        if fstype.is_mounted:
            mount = self.mount.value
        else:
            mount = None

        result = {
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        if self.size_limit:
            size = dehumanize_size(self.size.value)
            if size > self.size_limit:
                size = self.size_limit
            result["size"] = size
            result["partnum"] = self.partnum.value
        return result

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    partnum = IntegerField("Partition number")
    size = StringField()
    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def validate_size(self):
        v = self.size.value
        if not v:
            self.size.value = self.size_str
            return
        suffixes = ''.join(HUMAN_UNITS) + ''.join(HUMAN_UNITS).lower()
        if v[-1] not in suffixes:
            unit = self.size_str[-1]
            v += unit
            self.size.value = v
        try:
            sz = dehumanize_size(v)
        except ValueError as v:
            return str(v)
        if sz > self.size_limit:
            self.size.value = self.size_str
            self.size.show_extra(Color.info_minor(Text("Capped partition size at %s"%(self.size_str,), align="center")))

    def validate_mount(self):
        mountpoint = self.mount.value
        if mountpoint is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mountpoint) > 4095:
            return 'Path exceeds PATH_MAX'
        dev = self.mountpoint_to_devpath_mapping.get(mountpoint)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, mountpoint)


class _PartitionFormatView(BaseView):
    def __init__(self, model, controller, size_limit, edit_obj=None, include_delete=False):
        self.model = model
        self.controller = controller

        self.form = PartitionFormatForm(
            model.supported_filesystems,
            size_limit,
            model.get_mountpoint_to_devpath_mapping(edit_obj))

        if edit_obj is not None:
            self.form.initialize_from_object(edit_obj)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        body = [
            self.form.as_rows(self),
            Padding.line_break(""),
            ]

        if include_delete:
            delete_btn = PlainButton("Delete")
            connect_signal(delete_btn, 'click', self.delete)
            body.extend([
                Padding.fixed_10(Color.info_error(delete_btn)),
                Text(""),
                ])

        body.append(Padding.fixed_10(self.form.buttons))

        partition_box = Padding.center_50(ListBox(body))
        super().__init__(partition_box)


class AddPartitionView(_PartitionFormatView):

    def __init__(self, model, controller, disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(disk.path))
        self.disk = disk

        super().__init__(
            model,
            controller,
            disk.free)

        self.form.partnum.value = disk.next_partnum

    def cancel(self, button=None):
        self.controller.partition_disk(self.disk)

    def done(self, result):
        self.controller.add_disk_partition_handler(self.disk, self.form.result())


class EditPartitionView(_PartitionFormatView):

    def __init__(self, model, controller, partition):
        log.debug('EditPartitionView: selected_disk=[{}]'.format(partition.path))
        self.partition = partition

        super().__init__(
            model,
            controller,
            partition.device.free + partition.size,
            partition,
            include_delete=True)

    def cancel(self, button=None):
        self.controller.partition_disk(self.disk)

    def done(self, result):
        self.controller.update_partition(self.partition, self.form.result())

    def delete(self, sender):
        self.controller.delete_partition(self.partition)


class FormatEntireView(_PartitionFormatView):

    def __init__(self, model, controller, disk, back):
        log.debug('FormatEntireView: selected_disk=[{}]'.format(disk.path))
        self.disk = disk
        self.back = back

        super().__init__(
            model,
            controller,
            None,
            disk,
            include_delete=False)

    def cancel(self, button=None):
        self.back()

    def done(self, result):
        self.controller.add_format_handler(self.disk, self.form.result(), self.back)
