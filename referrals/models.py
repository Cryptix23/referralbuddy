from django.contrib.auth.models import User
from django.db import models

from social_auth.models import UserSocialAuth
from paypal.standard.ipn.signals import payment_was_successful

class Country(models.Model):

	name = models.CharField(max_length=100)
	code = models.CharField(max_length=3)

	def __unicode__(self):
		return self.name

	class Meta:
		verbose_name_plural = "Countries"

class Industry(models.Model):

	name = models.CharField(max_length=100)
	description = models.CharField(max_length=1000)
	entity_active = models.BooleanField()

	def __unicode__(self):
		return self.name

	class Meta:
		verbose_name_plural = "Industries"

class EntityContact(models.Model):

	first_name = models.CharField(max_length=100)
	last_name = models.CharField(max_length=100)
	email = models.CharField(max_length=100,default='')
	phone = models.CharField(max_length=100)

	def __unicode__(self):
		return '%s %s' % (self.first_name, self.last_name)

	class Meta:
		verbose_name_plural = "Entity Contacts"

class EntityReferral(models.Model):
	
	referrer = models.ForeignKey(User, related_name='referrer')
	referred = models.ManyToManyField(User, related_name='referred')
	organization = models.ForeignKey(User, related_name='entity_referred')
	department = models.ForeignKey('Department', blank=True, null=True)

	created_date = models.DateTimeField()
	updated_date = models.DateTimeField()
	entity_active = models.BooleanField()

	def __unicode__(self):
	 	return '%s %s made a referral' % (self.referrer.first_name, self.referrer.last_name)
			

	class Meta:
		verbose_name_plural = "Entity Referrals"

class ReferrerPoints(models.Model):

	referrer = models.ForeignKey(User, null=False, blank=False, related_name='points_referrer')
	organization = models.ForeignKey(User, related_name='points_org')
	value = models.IntegerField()
	entity_active = models.BooleanField()

	def __unicode__(self):
		return '%s %s has %d points with %s' % (self.referrer.first_name, self.referrer.last_name,
			self.value, self.organization.get_profile().business_name)

	class Meta:
		verbose_name_plural = "Referral Points"

class EntityPlan(models.Model):
	
	plan_name = models.CharField(max_length=100)
	price = models.CharField(max_length=10)
	plan_description = models.CharField(max_length=2000)
	max_referrals_allowed = models.IntegerField(null=True, blank=True)

	num_referrals_for_gift = models.IntegerField(null=True)
	direct_referal_value = models.FloatField(null=True, blank=True)
	indirect_referral_value = models.FloatField(null=True, blank=True)
	
	unlimited_referrals = models.BooleanField()
	can_add_entity = models.BooleanField()
	can_use_social_media = models.BooleanField()
	entity_active = models.BooleanField()

	def __unicode__(self):
		return "%s %s AUD" % (self.plan_name, self.price)

	class Meta:
		verbose_name_plural = "Entity Plans"


class Department(models.Model):

	department = models.CharField(max_length=100)

	def __unicode__(self):
		return self.department

	class Meta:
		ordering = ['department']

class EntityProfile(models.Model):
	
	entity_type = models.CharField(max_length=10)

	user = models.ForeignKey(User,null=False, blank=False)
	plan = models.ForeignKey(EntityPlan, blank=True, null=True)
	industry = models.ForeignKey(Industry, null=True, blank=True)
	entity_contact = models.ForeignKey(EntityContact)
	departments = models.ManyToManyField(Department, blank=True, null=True)

	referrals_made = models.IntegerField(null=True, blank=True)

	inherit_from_plan = models.BooleanField()
	
	business_name = models.CharField(max_length=100, null=True, blank=True)
	
	num_referrals_for_gift = models.IntegerField(null=True, blank=True, default=10)
	direct_referal_value = models.FloatField(null=True, blank=True)
	indirect_referral_value = models.FloatField(null=True, blank=True)

	address1 = models.CharField(max_length=100)
	city = models.CharField(max_length=100)
	suburb = models.CharField(max_length=100)
	state = models.CharField(max_length=100)
	country = models.ForeignKey(Country,blank=False,null=False)

	post_to_facebook = models.BooleanField(default=False)
	post_to_twitter = models.BooleanField(default=False)

	ipaddress = models.CharField(max_length=100, default=True, null=True)

	created_date = models.DateTimeField()
	updated_date = models.DateTimeField()
	entity_active = models.BooleanField()

	def get_facebook_token(self):
		from referrals.facebook import get_access_token
		return get_access_token(self.user)

	def is_facebook_user(self):
		return self.get_facebook_token()

	def is_twitter_user(self):
		try:
			user = UserSocialAuth.objects.get(user=self.user, provider='twitter')
			return True
		except UserSocialAuth.DoesNotExist:
			return False

	def is_organization(self):
		return self.entity_type == 'org'

	def __unicode__(self):
		if self.entity_type == 'org':
			return self.business_name
		return '%s %s' % (self.entity_contact.first_name, self.entity_contact.last_name)

	class Meta:
		verbose_name_plural = "Entity Profiles"



class FacebookPostMessage(models.Model):

	user = models.OneToOneField(UserSocialAuth)
	message = models.CharField(max_length=1000)
	link = models.CharField(max_length=100)

	def __unicode__(self):
		return self.message

	class Meta:
		verbose_name_plural = "Facebook Messages"

class TwitterPostMessage(models.Model):

	user = models.OneToOneField(UserSocialAuth)
	tweet = models.CharField(max_length=140)

	def __unicode__(self):
		return self.tweet

	class Meta:
		verbose_name_plural = "Twitter Tweets"

def paypal_ipn_return(sender, **kwargs):
	import logging
	log = logging.getLogger(__name__)
	log.debug(">>>>>>>>>>>>>>>>>>IPN RETURNED " + str(kwargs))

payment_was_successful.connect(paypal_ipn_return)