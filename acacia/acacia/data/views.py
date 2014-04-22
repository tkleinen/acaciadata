from django.views.generic.edit import CreateView
from django.views.generic.list import ListView
from django.views.generic import DetailView
from django.views.generic.base import TemplateView
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect
from .models import Project, ProjectLocatie, MeetLocatie, Datasource, Series, Chart, Dashboard
from .util import datasource_as_zip, datasource_as_csv, meetlocatie_as_zip, series_as_csv, chart_as_csv
import json
import datetime
import re
import logging

logger = logging.getLogger(__name__)

def DatasourceAsZip(request,pk):
    ds = get_object_or_404(Datasource,pk=pk)
    return datasource_as_zip(ds)

def MeetlocatieAsZip(request,pk):
    loc = get_object_or_404(MeetLocatie,pk=pk)
    return meetlocatie_as_zip(loc)

def DatasourceAsCsv(request,pk):
    ds = get_object_or_404(Datasource,pk=pk)
    return datasource_as_csv(ds)

def SeriesAsCsv(request,pk):
    s = get_object_or_404(Series,pk=pk)
    return series_as_csv(s)

def ChartAsCsv(request,pk):
    c = get_object_or_404(Chart,pk=pk)
    return chart_as_csv(c)

def UpdateMeetlocatieDirect(request,pk):
    loc = get_object_or_404(MeetLocatie,pk=pk)
    for d in loc.datasources.all():
        num = d.download()
        if num > 0:
            d.update_parameters()
            data = d.get_data()
            for p in d.parameter_set.all():
                for s in p.series_set.all():
                    s.update(data)
    referer = request.META.get('HTTP_REFERER',None)
    return redirect(referer)

from .tasks import update_meetlocatie

def UpdateMeetlocatie(request,pk):
    # TODO: prevent double task
    update_meetlocatie.delay(pk)
    referer = request.META.get('HTTP_REFERER',None)
    return redirect(referer)

class DatasourceDetailView(DetailView):
    model = Datasource

class ProjectView(DetailView):
    model = Project       
    
class ProjectListView(ListView):
    model = Project

class ProjectDetailView(DetailView):
    model = Project

    def get_context_data(self, **kwargs):
        context = super(ProjectDetailView, self).get_context_data(**kwargs)
        project = self.get_object()
        content = []
        for loc in project.projectlocatie_set.all():
            pos = loc.latlon()
            content.append({
                            'name': loc.name,
                            'lat': pos.y,
                            'lon': pos.x,
                            'info': render_to_string('data/projectlocatie_info.html', {'object': loc})
                            })
        context['content'] = json.dumps(content)
        context['maptype'] = 'TERRAIN'
        return context

class ProjectLocatieDetailView(DetailView):
    model = ProjectLocatie
    
    def get_context_data(self, **kwargs):
        context = super(ProjectLocatieDetailView, self).get_context_data(**kwargs)
        content = render_to_string('data/projectlocatie_info.html', {'object': self.get_object()})
        context['content'] = json.dumps(content)
        context['maptype'] = 'SATELLITE'
        context['zoom'] = 14
        return context

class MeetLocatieDetailView(DetailView):
    model = MeetLocatie
    
    def get_context_data(self, **kwargs):
        context = super(MeetLocatieDetailView, self).get_context_data(**kwargs)
        content = render_to_string('data/meetlocatie_info.html', {'object': self.get_object()})
        context['content'] = json.dumps(content)
        context['maptype'] = 'SATELLITE'
        context['zoom'] = 16
        return context
        
class SeriesView(DetailView):
    model = Series

    def get_context_data(self, **kwargs):
        context = super(SeriesView, self).get_context_data(**kwargs)
        ser = self.get_object()
        options = {
            'chart': {'type': ser.parameter.type, 'animation': False, 'zoomType': 'x'},
            'title': {'text': ser.name},
            'xAxis': {'type': 'datetime'},
            'yAxis': [],
            'tooltip': {'valueSuffix': ' '+ser.parameter.unit,
                        'valueDecimals': 2
                       }, 
            'legend': {'enabled': False},
            'plotOptions': {'line': {'marker': {'enabled': False}}},            
            'credits': {'enabled': True, 
                        'text': 'acaciawater.com', 
                        'href': 'http://www.acaciawater.com',
                       }
            }

        allseries = []
        title = ser.name if len(ser.parameter.unit)==0 else ser.parameter.unit
        options['yAxis'].append({
                                 'title': {'text': title},
                                 })
        pts = [[p.date,p.value] for p in ser.datapoints.all().order_by('date')]
        allseries.append({
                          'name': ser.name,
                          'type': ser.parameter.type,
                          'data': pts})
        options['series'] = allseries
        jop = json.dumps(options,default=date_handler)
        # remove quotes around date stuff
        jop = re.sub(r'\"(Date\.UTC\([\d,]+\))\"',r'\1', jop)
        context['options'] = jop
        return context
            
def tojs(d):
    return 'Date.UTC(%d,%d,%d,%d,%d,%d)' % (d.year, d.month-1, d.day, d.hour, d.minute, d.second)

def date_handler(obj):
    return tojs(obj) if isinstance(obj, datetime.date) or isinstance(obj, datetime.datetime) else obj

class ChartBaseView(TemplateView):
    template_name = 'data/plain_chart.html'

    def get_json(self, chart):
        options = {
            'chart': {'animation': False, 'zoomType': 'x'},
            'title': {'text': chart.title},
            'xAxis': {'type': 'datetime'},
            'yAxis': [],
            'tooltip': {'valueDecimals': 2,
                        'shared': True,
                       }, 
            'legend': {'enabled': chart.series.count() > 1},
            'plotOptions': {'line': {'marker': {'enabled': False}}},            
            'credits': {'enabled': True, 
                        'text': 'acaciawater.com', 
                        'href': 'http://www.acaciawater.com',
                       }
            }
        start = chart.auto_start()
        options['xAxis']['min'] = tojs(start)
#         if not chart.stop is None:
#             options['xAxis']['max'] = tojs(chart.stop)
        allseries = []
        for i,s in enumerate(chart.series.all()):
            ser = s.series
            title = s.label #ser.name if len(ser.unit)==0 else '%s [%s]' % (ser.name, ser.unit) if chart.series.count()>1 else ser.unit
            options['yAxis'].append({
                                     'title': {'text': title},
                                     'opposite': 0 if s.axislr == 'l' else 1,
                                     'min': s.y0,
                                     'max': s.y1
                                     })
            pts = [[p.date,p.value] for p in ser.datapoints.filter(date__gte=start).order_by('date')]
            allseries.append({
                              'name': ser.name,
                              'type': s.type,
                              'yAxis': s.axis-1,
                              'data': pts})
        options['series'] = allseries
        jop = json.dumps(options,default=date_handler)
        # remove quotes around date stuff
        jop = re.sub(r'\"(Date\.UTC\([\d,]+\))\"',r'\1', jop)
        return jop
    
    def get_context_data(self, **kwargs):
        context = super(ChartBaseView, self).get_context_data(**kwargs)
        pk = context.get('pk',1)
        chart = Chart.objects.get(pk=pk)
        jop = self.get_json(chart)
        context['options'] = jop
        return context
        
class ChartView(ChartBaseView):
    template_name = 'data/chart_detail.html'

    def get_context_data(self, **kwargs):
        context = super(ChartView, self).get_context_data(**kwargs)
        pk = context.get('pk',1)
        if pk is not None:
            chart = Chart.objects.get(pk=pk)
            jop = self.get_json(chart)
            context['options'] = jop
            context['chart'] = chart
        return context
    
class DashView(TemplateView):
    template_name = 'data/dash.html'
    
    def get_context_data(self, **kwargs):
        context = super(DashView,self).get_context_data(**kwargs)
        pk = context.get('pk', None)
        dash = get_object_or_404(Dashboard, pk=pk)
        context['dashboard'] = dash
        return context