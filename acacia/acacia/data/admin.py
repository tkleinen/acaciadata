from acacia.data.models import Project, ProjectLocatie, MeetLocatie, Series, DataFile, Generator, Parameter, DataPoint, Chart, ChartOptions, Dashboard
from acacia.data.shortcuts import meteo2locatie
from django.contrib import admin
from django import forms
from django.forms import PasswordInput, ModelForm
from django.contrib.gis.db import models
from django.forms.widgets import Textarea
from django.core import validators
import django.contrib.gis.forms as geoforms
import json
import logging
logger = logging.getLogger(__name__)

class LocatieInline(admin.TabularInline):
    model = ProjectLocatie
    options = {
        'extra': 0,
    }

class MeetlocatieInline(admin.TabularInline):
    model = MeetLocatie

class DataFileInline(admin.TabularInline):
    model = DataFile

class ParameterInline(admin.TabularInline):
    model = Parameter
    extra = 1
    fields = ('name', 'description', 'unit', 'datafile',)

class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_count', )

class ProjectLocatieForm(ModelForm):
    model = ProjectLocatie
    point = geoforms.PointField(widget=
        geoforms.OSMWidget(attrs={'map_width': 800, 'map_height': 500}))
        
class ProjectLocatieAdmin(admin.ModelAdmin):
    #form = ProjectLocatieForm
    list_display = ('name','project','location_count',)
    list_filter = ('project',)
    formfield_overrides = {models.PointField:{'widget': Textarea}}

class MeetLocatieForm(ModelForm):
    
    def clean_location(self):
        loc = self.cleaned_data['location']
        if loc is None:
            # set default location
            projectloc = self.cleaned_data['projectlocatie']
            loc = projectloc.location
        return loc
    
    def clean_name(self):
        # trim whitespace from name
        return self.cleaned_data['name'].strip()
    
def meteo_toevoegen(modeladmin, request, queryset):
    for loc in queryset:
        meteo2locatie(loc,user=request.user)
meteo_toevoegen.short_description = "Meteostation, neerslagstation en regenradar toevoegen"
    
class MeetLocatieAdmin(admin.ModelAdmin):
    form = MeetLocatieForm
    list_display = ('name','projectlocatie','project','filecount',)
    list_filter = ('projectlocatie','projectlocatie__project',)
    formfield_overrides = {models.PointField:{'widget': Textarea, 'required': False}}
    actions = [meteo_toevoegen]
    #inlines = [DataFileInline,]
    
def upload_datafile(modeladmin, request, queryset):
    for df in queryset:
        if df.url != '':
            df.download()
upload_datafile.short_description = "Upload de geselecteerde data files naar de server"

def update_parameters(modeladmin, request, queryset):
    for df in queryset:
        df.update_parameters()
update_parameters.short_description = "Update de parameterlijst van de geselecteerde data files"

def replace_parameters(modeladmin, request, queryset):
    for df in queryset:
        count = df.parameters()
        df.parameter_set.all().delete()
        logger.info('%d parameters deleted for datafile %s' % (count, df))
        df.update_parameters()    
replace_parameters.short_description = "Vervang de parameterlijst van de geselecteerde data files"

class DataFileForm(ModelForm):
    model = DataFile
    password = forms.CharField(label='Wachtwoord', help_text='Wachtwoord voor de webservice', widget=PasswordInput(render_value=True),required=False)

    def clean_config(self):
        config = self.cleaned_data['config']
        try:
            if config != '':
                json.loads(config)
        except Exception as ex:
            raise forms.ValidationError('Onjuiste JSON dictionary: %s'% ex)
        return config
    
class DataFileAdmin(admin.ModelAdmin):
    form = DataFileForm
    inlines = [ParameterInline,]
    actions = [upload_datafile, replace_parameters]
    list_filter = ('meetlocatie','meetlocatie__projectlocatie','meetlocatie__projectlocatie__project',)
    list_display = ('name', 'description', 'filename', 'filesize', 'filedate', 'start', 'stop', 'rows', 'cols', 'parameters',)
    fieldsets = (
                 ('Algemeen', {'fields': ('name', 'description', 'meetlocatie',),
                               'classes': ('grp-collapse grp-open',),
                               }),
                 ('Bronnen', {'fields': ('file', 'generator', 'url',('username', 'password'), 'config',),
                               'classes': ('grp-collapse grp-closed',),
                              }),
#                  ('Admin', {'fields': ('user',),
#                                'classes': ('grp-collapse grp-closed',),
#                             })
    )
    def save_model(self, request, obj, form, change):
        obj.user = request.user
        obj.save()
            

class GeneratorAdmin(admin.ModelAdmin):
    list_display = ('name', 'classname', 'description')

def update_thumbnails(modeladmin, request, queryset):
    # group queryset by datafile
    group = {}
    for p in queryset:
        if not p.datafile in group:
            group[p.datafile] = []
        group[p.datafile].append(p)
         
    for fil,parms in group.iteritems():
        data = fil.get_data()
        for p in parms:
            p.make_thumbnail(data=data)
            p.save()
    
update_thumbnails.short_description = "Thumbnails vernieuwen"

class ParameterAdmin(admin.ModelAdmin):
    list_filter = ('datafile',)
    actions = [update_thumbnails,]
    list_display = ('name', 'thumbtag', 'datafile', 'unit', 'description')

def refresh_series(modeladmin, request, queryset):
    for s in queryset:
        s.update()
refresh_series.short_description = 'Geselecteerde tijdreeksen actualiseren'

def replace_series(modeladmin, request, queryset):
    for s in queryset:
        s.replace()
replace_series.short_description = 'Geselecteerde tijdreeksen opnieuw aanmaken'

def series_thumbnails(modeladmin, request, queryset):
    for s in queryset:
        s.make_thumbnail()
        s.save() # saving a series will update the thumbnail
series_thumbnails.short_description = "Thumbnails van tijdreeksen vernieuwen"

class ReadonlyTabularInline(admin.TabularInline):
    can_delete = False
    extra = 0
    editable_fields = []
    
    def get_readonly_fields(self, request, obj=None):
        fields = []
        for field in self.model._meta.get_all_field_names():
            if (not field == 'id'):
                if (field not in self.editable_fields):
                    fields.append(field)
        return fields
    
    def has_add_permission(self, request):
        return False
    
class DataPointInline(ReadonlyTabularInline):
    model = DataPoint
        
class SeriesAdmin(admin.ModelAdmin):
    actions = [refresh_series, replace_series, series_thumbnails]
    list_display = ('name', 'thumbtag', 'parameter', 'datafile', 'unit', 'aantal', 'van', 'tot', 'minimum', 'maximum', 'gemiddelde')
    exclude = ('user',)
    def save_model(self, request, obj, form, change):
        obj.user = request.user
        obj.save()
 
class SeriesInline(admin.TabularInline):
    model = Series
        
class DataPointAdmin(admin.ModelAdmin):
    list_display = ('series', 'date', 'value',)
    list_filter = ('series', )
    ordering = ('series', 'date', )

class ChartAdmin(admin.ModelAdmin):
    filter_horizontal = ('series',)
    list_display = ('name', 'title', 'tijdreeksen', )

class DashAdmin(admin.ModelAdmin):
    filter_horizontal = ('charts',)
    list_display = ('name', 'description', 'grafieken',)
    exclude = ('user',)
    
    def save_model(self, request, obj, form, change):
        obj.user = request.user
        obj.save()
    
admin.site.register(Project, ProjectAdmin)
admin.site.register(ProjectLocatie, ProjectLocatieAdmin)
admin.site.register(MeetLocatie, MeetLocatieAdmin)
admin.site.register(Series, SeriesAdmin)
admin.site.register(Parameter, ParameterAdmin)
admin.site.register(Generator, GeneratorAdmin)
admin.site.register(DataFile, DataFileAdmin)
admin.site.register(DataPoint, DataPointAdmin)
admin.site.register(Chart, ChartAdmin)
admin.site.register(ChartOptions)
admin.site.register(Dashboard, DashAdmin)
