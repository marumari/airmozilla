import datetime

import mock
from nose.tools import eq_, ok_

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from funfactory.urlresolvers import reverse

from airmozilla.main.models import (
    Approval,
    Event,
    Channel,
    Template,
    Tag,
)
from airmozilla.base.tests.testbase import Response
from airmozilla.base.tests.testbase import DjangoTestCase


class TestFeeds(DjangoTestCase):

    def setUp(self):
        super(TestFeeds, self).setUp()
        # Make the fixture event live as of the test.
        event = Event.objects.get(title='Test event')
        event.start_time = timezone.now()
        event.archive_time = None
        event.save()

        self.main_channel = Channel.objects.get(
            slug=settings.DEFAULT_CHANNEL_SLUG
        )

    def test_feed(self):
        delay = datetime.timedelta(days=1)

        event1 = Event.objects.get(title='Test event')
        event1.status = Event.STATUS_SCHEDULED
        event1.start_time -= delay
        event1.archive_time = event1.start_time
        event1.save()
        eq_(Event.objects.archived().approved().count(), 1)
        eq_(Event.objects.archived().count(), 1)

        event = Event.objects.create(
            title='Second test event',
            description='Anything',
            start_time=event1.start_time,
            archive_time=event1.archive_time,
            privacy=Event.PRIVACY_COMPANY,  # Note!
            status=event1.status,
            placeholder_img=event1.placeholder_img,
        )
        event.channels.add(self.main_channel)

        eq_(Event.objects.archived().approved().count(), 2)
        eq_(Event.objects.archived().count(), 2)

        url = reverse('main:feed', args=('public',))
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' not in response.content)

        url = reverse('main:feed')  # public feed
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' not in response.content)

        url = reverse('main:feed', args=('company',))
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' in response.content)

    def test_feed_unapproved_events(self):
        event = Event.objects.get(title='Test event')
        assert event.is_public()
        assert event in Event.objects.live()
        assert event in Event.objects.live().approved()

        public_url = reverse('main:feed', args=('public',))
        private_url = reverse('main:feed', args=('private',))

        response = self.client.get(public_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        response = self.client.get(public_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)

        cache.clear()

        app = Approval.objects.create(event=event)
        response = self.client.get(public_url)
        eq_(response.status_code, 200)
        ok_('Test event' not in response.content)
        response = self.client.get(private_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)

        app.processed = True
        app.save()
        response = self.client.get(public_url)
        eq_(response.status_code, 200)
        ok_('Test event' not in response.content)
        response = self.client.get(private_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)

        cache.clear()

        app.approved = True
        app.save()
        response = self.client.get(public_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        response = self.client.get(private_url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)

    def test_feed_with_webm_format(self):
        delay = datetime.timedelta(days=1)

        event1 = Event.objects.get(title='Test event')
        event1.status = Event.STATUS_SCHEDULED
        event1.start_time -= delay
        event1.archive_time = event1.start_time
        vidly_template = Template.objects.create(
            name='Vid.ly Something',
            content='<script>'
        )
        event1.template = vidly_template
        event1.template_environment = {'tag': 'abc123'}
        event1.save()
        eq_(Event.objects.approved().count(), 1)
        eq_(Event.objects.archived().count(), 1)

        url = reverse('main:feed_format_type', args=('public', 'webm'))
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(
            '<link>https://vid.ly/abc123?content=video&amp;format=webm</link>'
            in response.content
        )

    def test_feed_cache(self):
        delay = datetime.timedelta(days=1)

        event = Event.objects.get(title='Test event')
        event.start_time -= delay
        event.archive_time = event.start_time
        event.save()

        url = reverse('main:feed')
        eq_(Event.objects.archived().approved().count(), 1)
        eq_(Event.objects.archived().count(), 1)
        response = self.client.get(url)
        ok_('Test event' in response.content)

        event.title = 'Totally different'
        event.save()

        response = self.client.get(url)
        ok_('Test event' in response.content)
        ok_('Totally different' not in response.content)

    def test_private_feeds_by_channel(self):
        channel = Channel.objects.create(
            name='Culture and Context',
            slug='culture-and-context',
        )
        delay = datetime.timedelta(days=1)

        event1 = Event.objects.get(title='Test event')
        event1.status = Event.STATUS_SCHEDULED
        event1.start_time -= delay
        event1.archive_time = event1.start_time
        event1.save()
        event1.channels.clear()
        event1.channels.add(channel)

        eq_(Event.objects.archived().approved().count(), 1)
        eq_(Event.objects.archived().count(), 1)

        event = Event.objects.create(
            title='Second test event',
            description='Anything',
            start_time=event1.start_time,
            archive_time=event1.archive_time,
            privacy=Event.PRIVACY_COMPANY,  # Note!
            status=event1.status,
            placeholder_img=event1.placeholder_img,
        )
        event.channels.add(channel)

        eq_(Event.objects.archived().approved().count(), 2)
        eq_(Event.objects.archived().count(), 2)
        eq_(Event.objects.filter(channels=channel).count(), 2)

        url = reverse(
            'main:channel_feed',
            args=('culture-and-context', 'public')
        )
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' not in response.content)

        # public feed
        url = reverse(
            'main:channel_feed_default',
            args=('culture-and-context',)
        )
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' not in response.content)

        url = reverse(
            'main:channel_feed',
            args=('culture-and-context', 'company')
        )
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Test event' in response.content)
        ok_('Second test event' in response.content)

    def test_feeds_by_channel_with_webm_format(self):
        channel = Channel.objects.create(
            name='Culture and Context',
            slug='culture-and-context',
        )
        delay = datetime.timedelta(days=1)

        event1 = Event.objects.get(title='Test event')
        event1.status = Event.STATUS_SCHEDULED
        event1.start_time -= delay
        event1.archive_time = event1.start_time
        vidly_template = Template.objects.create(
            name='Vid.ly Something',
            content='<script>'
        )
        event1.template = vidly_template
        event1.template_environment = {'tag': 'abc123'}
        event1.save()
        event1.channels.clear()
        event1.channels.add(channel)

        event = Event.objects.create(
            title='Second test event',
            description='Anything',
            start_time=event1.start_time,
            archive_time=event1.archive_time,
            privacy=Event.PRIVACY_PUBLIC,
            status=event1.status,
            placeholder_img=event1.placeholder_img,
        )

        event.channels.add(channel)

        eq_(Event.objects.approved().count(), 2)
        eq_(Event.objects.archived().count(), 2)
        eq_(Event.objects.filter(channels=channel).count(), 2)

        url = reverse(
            'main:channel_feed_format_type',
            args=('culture-and-context', 'public', 'webm')
        )
        response = self.client.get(url)
        eq_(response.status_code, 200)
        assert 'Second test event' in response.content
        ok_(
            '<link>https://vid.ly/abc123?content=video&amp;format=webm</link>'
            in response.content
        )

    def test_itunes_feed(self):
        url = reverse('main:itunes_feed')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        # expect no items in it...
        assert '<item>' not in response.content
        # but we can check some important itunes tags
        ok_('<itunes:explicit>clean</itunes:explicit>' in response.content)
        ok_(
            '<itunes:category text="Technology"></itunes:category>'
            in response.content
        )
        ok_('<language>en-US</language>' in response.content)
        ok_('<itunes:subtitle>' in response.content)
        ok_('<itunes:summary>' in response.content)
        ok_('<itunes:email>' in response.content)
        ok_('<itunes:name>' in response.content)
        ok_('<itunes:image href="http' in response.content)

    @mock.patch('requests.head')
    def test_itunes_feed_item(self, rhead):

        def mocked_head(url):
            if url == 'http://cdn.vidly/file.mp4':
                return Response('', 302, headers={
                    'Content-Type': 'video/mp5',
                    'Content-Length': '1234567',
                })
            else:
                return Response('', 302, headers={
                    'Location': 'http://cdn.vidly/file.mp4',
                })

        rhead.side_effect = mocked_head

        event = Event.objects.get(title='Test event')
        event.archive_time = timezone.now()
        event.template_environment = {'tag': 'abc123'}
        event.duration = 60 * 60 + 60 + 1
        event.short_description = 'Short "description"'
        event.description = 'Long <a href="http://www.peterbe.com">URL</a>'
        event.save()
        event.template.name = 'Vid.ly something'
        event.template.save()
        event.tags.add(Tag.objects.create(name='Tag1'))
        event.tags.add(Tag.objects.create(name='Tag2'))
        assert event in Event.objects.archived().approved().filter(
            privacy=Event.PRIVACY_PUBLIC,
            template__name__icontains='Vid.ly',
        )
        url = reverse('main:itunes_feed')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        assert '<item>' in response.content
        xml_ = response.content.split('<item>')[1].split('</item>')[0]
        ok_(event.title in xml_)
        ok_(event.short_description in xml_)
        ok_(
            event.description.replace('<', '&lt;').replace('>', '&gt;') in xml_
        )
        ok_('<itunes:duration>01:01:01</itunes:duration>' in xml_)
        ok_('<itunes:keywords>Tag1,Tag2</itunes:keywords>' in xml_)
