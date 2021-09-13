from __future__ import absolute_import, unicode_literals

import logging

from django.contrib import messages
from django.utils.translation import ugettext_lazy as _, ungettext

from mayan.apps.common.generics import (
    ConfirmView, MultipleObjectConfirmActionView, SingleObjectDetailView,
    SingleObjectListView
)
from mayan.apps.common.mixins import ExternalObjectMixin

from ..events import event_document_view
from ..forms import DocumentVersionDownloadForm, DocumentVersionPreviewForm
from ..models import Document, DocumentVersion
from ..permissions import (
    permission_document_download, permission_document_version_revert,
    permission_document_version_view, permission_document_tools,
)
from ..tasks import task_update_page_count

from .document_views import DocumentDownloadFormView, DocumentDownloadView

__all__ = (
    'DocumentVersionDownloadFormView', 'DocumentVersionDownloadView',
    'DocumentVersionListView', 'DocumentVersionRevertView',
    'DocumentVersionView'
)
logger = logging.getLogger(__name__)


class DocumentVersionDownloadFormView(DocumentDownloadFormView):
    form_class = DocumentVersionDownloadForm
    model = DocumentVersion
    pk_url_kwarg = 'pk'
    querystring_form_fields = (
        'compressed', 'zip_filename', 'preserve_extension'
    )
    viewname = 'documents:document_multiple_version_download'

    def get_extra_context(self):
        result = super(
            DocumentVersionDownloadFormView, self
        ).get_extra_context()

        result.update({
            'title': _('Download document version'),
        })

        return result


class DocumentVersionDownloadView(DocumentDownloadView):
    model = DocumentVersion
    pk_url_kwarg = 'pk'

    def get_item_filename(self, item):
        preserve_extension = self.request.GET.get(
            'preserve_extension', self.request.POST.get(
                'preserve_extension', False
            )
        )

        preserve_extension = preserve_extension == 'true' or preserve_extension == 'True'

        return item.get_rendered_string(preserve_extension=preserve_extension)


class DocumentVersionListView(ExternalObjectMixin, SingleObjectListView):
    external_object_class = Document
    external_object_permission = permission_document_version_view
    external_object_pk_url_kwarg = 'pk'

    def get_document(self):
        document = self.external_object
        document.add_as_recent_document_for_user(user=self.request.user)
        return document

    def get_extra_context(self):
        return {
            'hide_object': True,
            'list_as_items': True,
            'object': self.get_document(),
            'table_cell_container_classes': 'td-container-thumbnail',
            'title': _('Versions of document: %s') % self.get_document(),
        }

    def get_source_queryset(self):
        return self.get_document().versions.order_by('-timestamp')


class DocumentVersionRevertView(ExternalObjectMixin, ConfirmView):
    external_object_class = DocumentVersion
    external_object_permission = permission_document_version_revert
    external_object_pk_url_kwarg = 'pk'

    def get_extra_context(self):
        return {
            'message': _(
                'All later version after this one will be deleted too.'
            ),
            'object': self.get_object().document,
            'title': _('Revert to this version?'),
        }

    def get_object(self):
        return self.external_object

    def view_action(self):
        try:
            self.get_object().revert(_user=self.request.user)
            messages.success(
                message=_(
                    'Document version reverted successfully'
                ), request=self.request
            )
        except Exception as exception:
            messages.error(
                message=_('Error reverting document version; %s') % exception,
                request=self.request
            )


class DocumentVersionUpdatePageCountView(MultipleObjectConfirmActionView):
    model = DocumentVersion
    object_permission = permission_document_tools
    success_message = _(
        '%(count)d document version queued for page count recalculation'
    )
    success_message_plural = _(
        '%(count)d documents version queued for page count recalculation'
    )

    def get_extra_context(self):
        queryset = self.object_list

        result = {
            'title': ungettext(
                singular='Recalculate the page count of the selected document version?',
                plural='Recalculate the page count of the selected document versions?',
                number=queryset.count()
            )
        }

        if queryset.count() == 1:
            result.update(
                {
                    'object': queryset.first(),
                    'title': _(
                        'Recalculate the page count of the document version: %s?'
                    ) % queryset.first()
                }
            )

        return result

    def object_action(self, form, instance):
        task_update_page_count.apply_async(
            kwargs={'version_id': instance.pk}
        )


class DocumentVersionView(SingleObjectDetailView):
    form_class = DocumentVersionPreviewForm
    model = DocumentVersion
    object_permission = permission_document_version_view

    def dispatch(self, request, *args, **kwargs):
        result = super(
            DocumentVersionView, self
        ).dispatch(request, *args, **kwargs)
        self.get_object().document.add_as_recent_document_for_user(
            request.user
        )
        event_document_view.commit(
            actor=request.user, target=self.get_object().document
        )

        return result

    def get_extra_context(self):
        return {
            'hide_labels': True,
            'object': self.get_object(),
            'title': _('Preview of document version: %s') % self.get_object(),
        }
