import os,datetime,urllib2,cgi
from django.db import models
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from acacia import settings

import logging
logger = logging.getLogger(__name__)

def project_upload(instance, filename):
    return '/'.join(['images', instance.name, filename])

class Project(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True,verbose_name='omschrijving')
    image = models.ImageField(upload_to=project_upload, blank = True, null=True)
    
    def locaties(self):
        return self.projectlocatie_set.count()
    
    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'projecten'

def locatie_upload(instance, filename):
    return '/'.join(['images', instance.project.name, instance.name, filename])

class ProjectLocatie(models.Model):
    project = models.ForeignKey(Project)
    name = models.CharField(max_length=50,verbose_name='naam')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    xcoord = models.FloatField()
    ycoord = models.FloatField()
    image = models.ImageField(upload_to=locatie_upload, blank = True, null = True)

    def meetlocaties(self):
        return self.meetlocatie_set.count()

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name',]

def meetlocatie_upload(instance, filename):
    return '/'.join(['images', instance.project.name, instance.projectlocatie.name, instance.name, filename])

class MeetLocatie(models.Model):
    projectlocatie = models.ForeignKey(ProjectLocatie)
    name = models.CharField(max_length=50,verbose_name='naam')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    xcoord = models.FloatField()
    ycoord = models.FloatField()
    image = models.ImageField(upload_to=meetlocatie_upload, blank = True, null = True)

    def project(self):
        return self.projectlocatie.project
        
    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name',]
        
def classForName( kls ):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__( module )
    for comp in parts[1:]:
        m = getattr(m, comp)            
    return m

class Generator(models.Model):
    name = models.CharField(max_length=50,verbose_name='naam')
    classname = models.CharField(max_length=50,verbose_name='python klasse naam',
                                 help_text='volledige naam van de generator klasse, bijvoorbeeld acacia.data.generators.knmi')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    
    def get_class(self):
        return classForName(self.classname)
    
    def __unicode__(self):
        return self.name
    
class DataFile(models.Model):
    name = models.CharField(max_length=50,verbose_name='naam')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    meetlocaties=models.ManyToManyField(MeetLocatie,related_name='datafiles',help_text='meetlocaties die gebruik maken van deze datafile')
    file=models.FileField(upload_to='datafiles',blank=True)
    url=models.CharField(blank=True,max_length=200,help_text='volledige url van de remote file. Leeg laten voor handmatige uploads')
    autorefresh=models.BooleanField(default=True,verbose_name='Automatische upload',help_text='Bestand automatisch uploaden als datafile bewaard wordt')
    generator=models.ForeignKey(Generator,blank=True, null=True,help_text='Generator voor het maken van tijdseries uit de datafile')
    created = models.DateTimeField(auto_now_add=True)
    uploaded = models.DateTimeField(auto_now=True)
    user=models.ForeignKey(User,default=User)
    
    @property
    def filename(self):
        return os.path.basename(self.file.name)
    #filename.short_description = 'bestandsnaam'

    @property
    def filesize(self):
        try:
            return os.path.getsize(os.path.join(settings.MEDIA_ROOT,self.file.name))
        except:
            # file may not (yet) exist
            return ''
    #filesize.short_description = 'grootte'

    @property
    def filedate(self):
        try:
            return datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(settings.MEDIA_ROOT,self.file.name)))
        except:
            # file may not (yet) exist
            return ''
    #filedate.short_description = 'datum'
    
    def __unicode__(self):
        return self.filename

    def get_absolute_url(self):
        return r'/data/%i/' % self.id 
    
    def download(self,save=True):
        response = urllib2.urlopen(self.url)
        if response is not None:
            if self.url.startswith('ftp'):
                filename = os.path.basename(self.url)
            else:
                _,params = cgi.parse_header(response.headers.get('Content-Disposition',''))
                filename = params.get('filename','file.txt')
            # oude file weggooien
            # self.file.delete(False)
            self.file.save(name=filename, content=ContentFile(response.read()), save=save)
    
    def update_parameters(self):
        gen = self.generator.get_class()
        params = gen().get_parameters(self.file)
        for p in params:
            theparam = self.parameter_set.get_or_create(**p)
            theparam.save()
            
    def parameters(self):
        return self.parameter_set.count()
    
from django.db.models.signals import pre_delete, pre_save
from django.dispatch.dispatcher import receiver

@receiver(pre_delete, sender=DataFile)
def datafile_delete(sender, instance, **kwargs):
    instance.file.delete(False)

@receiver(pre_save, sender=DataFile)
def datafile_save(sender, instance, **kwargs):
    if instance.url != '' and instance.autorefresh == True:
        instance.download(False)
        
class Parameter(models.Model):
    datafile = models.ForeignKey(DataFile)
    name = models.CharField(max_length=50,verbose_name='naam')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    unit = models.CharField(max_length=10, default='m',verbose_name='eenheid')

    def __unicode__(self):
        return self.name

class Series(models.Model):
    name = models.CharField(max_length=50,verbose_name='naam')
    description = models.TextField(blank=True,verbose_name='omschrijving')
    unit = models.CharField(max_length=10, blank=True, verbose_name='eenheid')
    parameter = models.ForeignKey(Parameter,null=True,blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name = 'tijdreeks'
        verbose_name_plural = 'tijdreeksen'
        
class DataPoint(models.Model):
    series = models.ForeignKey(Series,related_name='datapoints')
    date = models.DateTimeField()
    value = models.FloatField()
    