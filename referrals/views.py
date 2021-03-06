from datetime import datetime, timedelta

import urlparse
import urllib2, urllib
import base64

from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils import simplejson
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.sites.models import Site
from django.template.loader import render_to_string

from social_auth.models import UserSocialAuth

from celery.result import AsyncResult
import twitter

from paypal.standard.forms import PayPalPaymentsForm
from paypal.standard.ipn.models import PayPalIPN
from postman.forms import WriteForm

from referrals import models
from referrals.tasks import CalculateGifts
from decorators.profile import check_profile
from decorators.subscription import check_subscription
from referrals.facebook_sdk import GraphAPI, GraphAPIError

import utils

import logging
log = logging.getLogger(__name__)


def get_plan_price(request):
    if request.POST.get('plan_id'):
        plan = models.EntityPlan.objects.get(id=request.POST.get('plan_id'))
        return HttpResponse(simplejson.dumps([dict(status = 200, price = plan.price, name = plan.plan_name)]),content_type = 'application/javascript')
    return HttpResponse(simplejson.dumps([dict(status = 500)]),content_type = 'application/javascript')
    
@login_required
def create_profile(request,template='create_profile.html'):
    from referrals import forms
    
    if request.method == 'GET':
        
        paypal_dict = dict(
                    cmd = "_xclick-subscriptions",
                    business =  settings.PAYPAL_RECEIVER_EMAIL,
                    a3 = "9.99",                      # monthly price 
                    p3 = "1",                           # duration of each unit (depends on unit)
                    t3 =  "M",                         # duration unit ("M for Month")
                    src = "1",                        # make payments recur
                    sra = "0",                        # reattempt payment on payment error
                    no_note =  "1",                    # remove extra notes (optional)
                    item_name =  settings.PAYPAL_ITEM_NAME,
                    return_url =  settings.PAYPAL_RETURN_URL,
                    cancel_return =  settings.PAYPAL_CANCEL_RETURN_URL,
                    custom = request.user.username,
            )

        form1 = PayPalPaymentsForm(initial=paypal_dict, button_type="subscribe")

        form = forms.CreateProfileForm(instance=None)
        
        return render_to_response(template,
                              dict(
                                    title ='Creating a Profile',
                                    form  = form,
                                    form1 = form1,
                                    editing = False,
                                ),
                              context_instance=RequestContext(request))

    else:
        data = request.POST.copy()
        data['ipaddress'] = request.META.get('REMOTE_ADDR')
        form = forms.CreateProfileForm(user=request.user, data=data)
        if form.is_valid():
            profile = form.save()
            return HttpResponse(simplejson.dumps([dict(status = 200)]),content_type = 'application/javascript')

        errors = form.errors
        return HttpResponse(simplejson.dumps([dict(status = 500, errors = errors)]), content_type = 'application/javascript')

@login_required
@check_profile
def edit_profile(request, template='create_profile.html'):
    from referrals import forms

    editing = True

    if request.method == 'GET':
        form = forms.CreateProfileForm(instance=request.user.get_profile())
        return render_to_response(template,
                              dict(
                                    title ='Updating your Profile',
                                    form  = form,
                                    editing = editing,
                                ),
                              context_instance=RequestContext(request))
    else:
        form = forms.CreateProfileForm(data=request.POST, instance=request.user.get_profile())

        if form.is_valid():
            form.save()
            return HttpResponse(simplejson.dumps([dict(status = 200)]),content_type = 'application/javascript')

        else:
            return HttpResponse(simplejson.dumps([dict(status = 500)]),content_type = 'application/javascript')

@login_required
@check_profile
@check_subscription
def add_referral(request):

    from referrals import forms
    
    if request.method == 'GET':
        form = forms.CreateUserForm(prefix='referrer')
        form1 = forms.CreateUserForm(prefix='referred')
        form2 = forms.CreateReferralForm(organization=request.user)

    else:
        
        #check that org has not exceeded max referrals allowed
        profile = request.user.get_profile()
        referral_allowed = False

        if profile.plan.unlimited_referrals:
            referral_allowed = True

        if profile.plan.max_referrals_allowed > profile.referrals_made:
            referral_allowed = True

        if not referral_allowed:
            return render_to_response('referral_not_allowed.html',
                    dict(title='Referral Not Allowed',message = 'You have exceeded your referrals'),
                        context_instance=RequestContext(request))

        import random
        tmp_password = random.getrandbits(128)

        form = forms.CreateUserForm(user=request.user, tmp_password=tmp_password, data=request.POST, prefix='referrer')
        form1 = forms.CreateUserForm(user=request.user, tmp_password=tmp_password, data=request.POST, prefix='referred')

        data = request.POST.copy()
        data['organization'] = request.user.pk

        form2 = forms.CreateReferralForm(organization=request.user, data=data)

        if form.is_valid() and form1.is_valid():
            referrer = form.save()
            referred = form1.save()

            data['referrer'] = referrer.pk
            data['referred'] = referred.pk

            if form2.is_valid():
                referral = form2.save()
            else:
                return render_to_response('message.html',
                        dict(title='Invalid Referral!', message=form2.non_field_errors),
                        context_instance=RequestContext(request))


            # +1 on number of referrals this organization has recorded
            profile.referrals_made += 1
            profile.save()              

            #send email to referrer and referred
            from mailer import send_new_user_email
            send_new_user_email(referrer=referrer, referred=referred, business_name=request.user.get_profile().business_name)

            if request.POST.get('action') == 'add_another':
                form1 = forms.CreateUserForm(prefix='referred')
                return render_to_response('add_referral.html',
                    dict(title='Adding A Referral',
                        form = form,
                        form1 = form1,
                        referral_id = referral.pk),
                        context_instance=RequestContext(request))
            else:
                #add a referrer point for this referral
                try:
                    referral_point = models.ReferrerPoints.objects.get(referrer=referrer.pk, organization=request.user)
                    referral_point.value += request.user.get_profile().direct_referal_value
                    referral_point.save()
                except models.ReferrerPoints.DoesNotExist:
                    referral_point = models.ReferrerPoints(referrer=referrer, organization=request.user, entity_active=True, value=request.user.get_profile().direct_referal_value)

                    referral_point.save()

                utils.calculate_points([referrer.pk,], value=request.user.get_profile().indirect_referral_value)

            return render_to_response('message.html',
                        dict(title='Referral Added!', message="Your Referral Has Been Added"),
                        context_instance=RequestContext(request))
                
    return render_to_response('add_referral.html',
                dict(title='Adding A Referral',
                    form = form,
                    form1 = form1,
                    form2 = form2),
                context_instance=RequestContext(request))

@login_required
@check_profile
@check_subscription
def calculate_gifts(request, template='calcluate_gifts_wait.html'):
    
    task = CalculateGifts.delay(request.user)
    request.session['task_id'] = task.id
    return render_to_response(template,
                    dict(),
                    context_instance=RequestContext(request))

def calculate_gifts_check(request):
    if request.method == 'GET':
        task_id = request.session.get('task_id', None)
        if task_id:
            result = AsyncResult(task_id)
            if result.ready():
                return HttpResponse(simplejson.dumps([dict(status = 200)]), content_type = 'application/javascript; charset=utf8')
            else:
                return HttpResponse(simplejson.dumps([dict(status = 100)]), content_type = 'application/javascript; charset=utf8')
    return HttpResponse(simplejson.dumps([dict(status = 500)]), content_type = 'application/javascript; charset=utf8')


def referrer_first_login(request, b64email):
    from referrals import forms
    if request.method == 'GET':
        email = base64.b64decode(b64email)
        u = User.objects.get(email=email)
        if u.is_active:
            return HttpResponseRedirect(reverse('auth_login'))
        form = forms.FirstLoginForm(initial=dict(email=email))
        return render_to_response('referrer_first_login.html',
                dict(title='First Login',form = form),
                context_instance=RequestContext(request))

    else:
        form = forms.FirstLoginForm(data=request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(username=form.cleaned_data['email'], password=form.cleaned_data['password1'])
            login(request, user)
            return HttpResponseRedirect('/')
        return render_to_response('referrer_first_login.html',
                dict(title='First Login',form = form),
                context_instance=RequestContext(request))

@login_required
@check_profile
@check_subscription
def view_referrers(request):
    referrals = models.EntityReferral.objects.filter(organization__email=request.user.email)

    if len(referrals) == 0:
        return render_to_response('no_referrers.html',
                dict(title='Error!',),
                context_instance=RequestContext(request))
        
    aaData = []
    for referral in referrals:
        sublist = []
        sublist.append(str(referral.referrer.first_name))
        sublist.append(str(referral.referrer.last_name))
        sublist.append(str(models.ReferrerPoints.objects.get(referrer__email=referral.referrer.email, organization__email=request.user.email).value))
        aaData.append(sublist)


    return render_to_response('referrers.html',
            dict(title='Viewing Referrers',aaData = aaData),
            context_instance=RequestContext(request))

@login_required
@check_profile
def view_referred(request):

    referrals = models.EntityReferral.objects.filter(referrer__email=request.user.email)
    if len(referrals) == 0:
        return render_to_response('none_referred.html',
                dict(title='No Referrals',),
                context_instance=RequestContext(request))

    aaData = []
    for referral in referrals:
        referred = referral.referred.all()
        for r in referred:
            sublist = []
            sublist.append(str(r.first_name))
            sublist.append(str(r.last_name))
            sublist.append(str(referral.organization.get_profile().business_name))
            aaData.append(sublist)


    return render_to_response('referred.html',
            dict(title='Viewing Referrers',aaData = aaData),
            context_instance=RequestContext(request))

def add_referral_autocomplete(request):
    if request.method == 'POST':
        search = request.POST.get('email')
        users = User.objects.filter(email__icontains=search)
        result = [dict(email = user.email, first_name = user.first_name, last_name = user.last_name, dob = datetime.strftime(user.dob,'%d/%m/%Y') if user.dob else '') for user in users]
        return HttpResponse(simplejson.dumps(result))
    return HttpResponse(simplejson.dumps([dict(status = 500)]))

@login_required
@check_profile
def post_to_facebook(request):
    from referrals import forms

    try:
        instance = models.FacebookPostMessage.objects.get(user=request.user.social_user.id if hasattr(request.user, 'social_user') \
            else UserSocialAuth.objects.get(user=request.user.id, provider='facebook'))
    except models.FacebookPostMessage.DoesNotExist:
        instance = None

    if request.method == 'GET':

        form = forms.FacebookPostForm(user=request.user.social_user if hasattr(request.user, 'social_user') \
                                           else UserSocialAuth.objects.get(user=request.user.id, provider='facebook'),
                                       instance=instance)
        return render_to_response('post_to_facebook.html',
            dict(title='Posting to Facebook',form=form),
            context_instance=RequestContext(request))

    else:
        request.user.get_profile().post_to_facebook = True
        request.user.get_profile().save()

        form = forms.FacebookPostForm(data=request.POST, instance=instance)
        if form.is_valid():
            message = form.save()
            graph = GraphAPI(request.user.get_profile().get_facebook_token())
            
            attachment = dict(
                description = message.message
            )
            
            if message.link or message.link != '':
                attachment['link'] = message.link
    
            try:
                graph.put_wall_post(message, attachment)
            except GraphAPIError, e:
                if int(e.result['error']['code']) == 200:
                    return render_to_response('facebook_authorize_app.html',
                        dict(title='Viewing Referrers',),
                        context_instance=RequestContext(request))
        
            return render_to_response('message.html',
                dict(title='Message Posted', message='Your message was posted to facebok and will be posted once a week'),
                context_instance=RequestContext(request))

        return render_to_response('post_to_facebook.html',
            dict(title='Posting to Facebook',form=form),
            context_instance=RequestContext(request))

@login_required
@check_profile
def post_to_twitter(request):
    from referrals import forms

    try:

        user = request.user.social_user if hasattr(request.user, 'social_user') \
                else UserSocialAuth.objects.get(user=request.user.id, provider='twitter')
    except UserSocialAuth.DoesNotExist:
        return render_to_response('message.html',
                        dict(title='Invalid Account!', message='Please login with your twitter account'),
                        context_instance=RequestContext(request))

    try:
        instance = models.TwitterPostMessage.objects.get(user=user)
    except models.TwitterPostMessage.DoesNotExist:
        instance = None

    if request.method == 'GET':

        form = forms.TwitterPostForm(user=user, instance=instance)

        return render_to_response('post_to_twitter.html',
            dict(title='Posting to Twitter',form=form),
            context_instance=RequestContext(request))

    else:
        request.user.get_profile().post_to_twitter = True
        request.user.get_profile().save()

        form = forms.TwitterPostForm(data=request.POST, instance=instance)
        if form.is_valid():
            tweet = form.save()
        
            d = urlparse.parse_qs(user.extra_data['access_token'])
            api = twitter.Api(consumer_key=settings.TWITTER_CONSUMER_KEY, consumer_secret=settings.TWITTER_CONSUMER_SECRET, access_token_key=d['oauth_token'][0], access_token_secret=d['oauth_token_secret'][0])
        
            try:
                status = api.PostUpdate(tweet.tweet)
            except Exception, e:
                return render_to_response('message.html',
                        dict(title='Invalid Tweet!', message='This is a duplicate tweet'),
                        context_instance=RequestContext(request))


            return render_to_response('message.html',
                        dict(title='Message Posted', message='Your message was posted to Twitter and will be posted once a week'),
                        context_instance=RequestContext(request))

        return render_to_response('post_to_twitter.html',
            dict(title='Posting to Twitter',form=form),
            context_instance=RequestContext(request))


@login_required
@check_profile
@check_subscription
def search_referrers(request):
    if request.method == 'GET':
        return render_to_response('search_referrers.html',
            dict(title='Search For Referrers'),
            context_instance=RequestContext(request))

    else:
        first_name = request.POST.get('first_name','').replace('*', '')
        last_name = request.POST.get('last_name','').replace('*', '')
        business_name = request.POST.get('business_name','').replace('*', '')
        email = request.POST.get('email','').replace('*', '')

        referrers = models.EntityReferral.objects.filter(referrer__first_name__icontains=first_name,
                        referrer__last_name__icontains=last_name,
                        referrer__email__icontains=email,
                        organization__entityprofile__business_name__icontains=business_name
            )

        results = [[str(referrer.referrer.first_name), 
                str(referrer.referrer.last_name), 
                str(referrer.referrer.email),
                str('%s %s' % (referrer.referred.get().first_name, referrer.referred.get().last_name)),
                str(referrer.organization.get_profile().business_name),
                str(referrer.department if referrer.department else '')] for referrer in referrers]
        
        

        return render_to_response('search_referrers.html',
            dict(title='Search For Referrers', results=results),
            context_instance=RequestContext(request))

@login_required
@check_profile
@check_subscription
def search_organization(request):
    if request.method == 'GET':
        return render_to_response('search_organizations.html',
            dict(title='Search For Referrers'),
            context_instance=RequestContext(request))

    else:
        business_name = request.POST.get('business_name','').replace('*', '')
        country = request.POST.get('country','').replace('*', '')
        industry = request.POST.get('industry','').replace('*', '')
        state = request.POST.get('state','').replace('*', '')

        organizations = models.EntityProfile.objects.filter(business_name__icontains=business_name,
                    country__name__icontains=country,
                    industry__name__icontains=industry,
                    state__icontains=state
            )

        

        results = [[
                str(base64.b64encode('%s&%s' % (organization.entity_contact.id, organization.entity_contact.email))),
                str(organization.business_name),
                str(organization.industry.name), 
                str(organization.state),
                str(organization.country.name), 
                str(organization.entity_contact.first_name), 
                str(organization.entity_contact.last_name), 
                str(organization.entity_contact.email)] for organization in organizations]
        
        
        if request.is_ajax():
            template = 'ajax_org_results.html'
        else:
            template = 'search_organizations.html'

        return render_to_response(template,
            dict(title='Search For Referrers', results=results),
            context_instance=RequestContext(request))


@login_required
@check_profile
@check_subscription
def send_message(request, template='send_message.html'):
    saved = False
    org = False
    if request.method == 'GET':
        if request.GET.get('org_id'):
            data = base64.b64decode(request.GET.get('org_id')).split('&')
            entity_contact = models.EntityContact.objects.get(id=data[0], email=data[1])
            
            org = entity_contact.entityprofile_set.get()
            form = WriteForm(initial = dict(recipients = org.user.username))
        
        else:
            form = WriteForm()
    else:
        form = WriteForm(sender=request.user, data=request.POST)
        if form.is_valid():
            org = form.cleaned_data.get('recipients')[0].get_profile()
            if form.save():
                form.instance.moderation_status = "a"
                form.instance.save()
            saved = True
        else:
            if request.POST.get('recipients'):
                org = User.objects.get(username=request.POST.get('recipients')).get_profile()
    
    return render_to_response(template,
            dict(title='Send a Private Message', form = form, saved = saved, org = org),
            context_instance=RequestContext(request))


@csrf_exempt
def paypal_ipn(request, *args, **kwargs):
    
    try:
        #validate that this ipn was initiated from the site
        if request.POST.get('receiver_email') != settings.PAYPAL_RECEIVER_EMAIL:
            log.error('Received maliscious IPN.  Possible thread!  IPN DATA = %s' % request.POST)

        data = request.POST.copy()

        username = request.POST.get('custom')
        user = User.objects.get(username=username)
        profile = user.get_profile()
        
        #make sure the user is verified
        if data.get('payer_status') != 'verified':
            log.error('user %s is not active in paypal' % username)
            return HttpResponse('error')

        if data.get('txn_type') == 'subscr_signup':
            log.warn('received singup IPN with data %s' % (data))
            utils.create_subscription(user, data, profile.ipaddress)
        elif data.get('txn_type') == 'subscr_payment':
            log.warn('received subscr_payment IPN with data %s' % (data))
            utils.activate_subscription(user, data, profile.ipaddress)
            #now email the user that their subscription is active
            from mailer import send_email as send_mail
            send_mail(template='subscription_active', subject="Your Subscription is activated", to_email=[user.email])

    except Exception, e:
        log.error("Error occured in IPN %s" % e.message)
        return HttpResponse('error')

    return HttpResponse('ok')


def subscription_inactive(request, template='message.html'):
    return render_to_response(template,
                              dict(title='Your Subscription Is Inactive', message='Your Subscription Is Inactive',),
                              context_instance=RequestContext(request))

def subscription_pending(request, template='message.html'):
    return render_to_response(template,
                              dict(title='Your Subscription Is Inactive', message="""Your Subscription Is Pending.  You Will receive an email when it is active""",),
                              context_instance=RequestContext(request))

def rb_paypal_return(request, *args, **kwargs):
    return HttpResponseRedirect(reverse('home'))

def rb_paypal_cancel(request, *args, **kwagrs):
    return HttpResponseRedirect(reverse('home'))
