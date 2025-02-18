from abc import ABC
import re
from django.http.response import HttpResponse, HttpResponseRedirect

from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.forms import ModelForm, TextInput, EmailInput, NumberInput
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied, BadRequest
from django.shortcuts import render, redirect
from django.forms import formset_factory
from django.utils.text import slugify
from django.db.models import Q
from django.db import models
from django import forms

from rest_framework.renderers import JSONRenderer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework import renderers
from rest_framework import status

from user.models import CustomUser, Report_Class, Report_Answer, Report_Question
from hitcount.views import HitCountDetailView
from .serializer import QuestionSerializer
from category.models import Category
from answer.forms import AnswerForm

from answer.models import Answer
from comment.forms import CommentForm
from .forms import QuestionForm, ReportForm
from .models import Question, Tag


# Question - REST framework
class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer

    def form_valid(self, form):
        current_user = self.request.user
        if current_user.is_authenticated:
            form.instance.user_id = current_user
            ques_point_str = self.request.POST.get('ques_point')
            ques_point_str = form.fields['ques_point']
            new_ques = CustomUser()
            if ques_point_str:
                user = CustomUser.objects.get(username=current_user)
                user.ques_point = str(int(user.left_ques()) - int(self.request.POST.get('ques_point')))
                user.save()
            return super(QuestionCreate, self).form_valid(form)
        else:
            return redirect()

    # queryset 정의
    def get_queryset(self):
        queryset = self.queryset
        search_pk = self.request.query_params.get('pk', None)
        search_keyword = self.request.query_params.get('keyword', None)
        query_list = []
        if search_pk:
            queryset = queryset.filter(pk=search_pk)
        if search_keyword:
            queryset = queryset.filter(
                Q(ques_title__contains=search_keyword)
                | Q(ques_desc__contains=search_keyword)
                | Q(category_id__slug__contains=search_keyword)
            ).distinct()
        return queryset

    # url: viewset/question/questions/
    # url: viewset/question/questions/?pk={pk}?keyword={keyword}
    @action(detail=False)
    def questions(self, request):
        queryset = self.get_queryset()
        # print(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # url: viewset/question/create_question
    @action(detail=False, methods=['post'])
    def create_question(self, request):
        question = QuestionSerializer(data=request.data)
        if question.is_valid():
            question.save()
            return Response(question.data, status=status.HTTP_201_CREATED)
        return Response(question.errors, status=status.HTTP_400_BAD_REQUEST)

    # url: viewset/question/{pk}/update_question
    @action(detail=True, methods=['post'])
    def update_question(self, request, pk):
        instance = self.queryset.get(pk=pk)
        question = QuestionSerializer(instance, data=request.data, partial=True)
        print(question)
        if question.is_valid():
            question.save()
            return Response(question.data, status=status.HTTP_201_CREATED)
        return Response(question.errors, status=status.HTTP_400_BAD_REQUEST)


# 작동 문제 없음
class QuestionList(ListView):
    model = Question
    template_name = 'question/question_list.html'
    ordering = '-pk'
    paginate_by = 8

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(QuestionList, self).get_context_data()
        context['categories'] = Category.objects.all()
        context['no_category_question_count'] = Question.objects.filter(category_id=None).count()
        page_size = 5
        start_index = int((context['page_obj'].number - 1) / page_size) * page_size
        end_index = min(start_index + page_size, len(context['paginator'].page_range))
        context['page_range'] = context['paginator'].page_range[start_index: end_index]
        context['ranks'] = CustomUser.objects.filter(answer_count__gt=0).order_by('-answer_point', '-chosen_count')[:10]
        if Question.objects.all():
            pop_question = Question.objects.order_by("-hit_count_generic__hits")[0]
            if pop_question:
                context['pop_question'] = pop_question
            hot_question = Question.objects.order_by("-answer")[0]
            if hot_question:
                context['hot_question'] = hot_question
            expensive_question = Question.objects.order_by("-ques_point")[0]
            if expensive_question:
                context['expensive_question'] = expensive_question
            if Question.objects.filter(who_chosen=None):
                difficult_question = Question.objects.filter(who_chosen=None).order_by("-post_date")[0]
                if difficult_question:
                    context['difficult_question'] = difficult_question
        return context


# 작동 문제 없음
class QuestionDetail(HitCountDetailView):
    model = Question
    template_name = 'question/question_detail.html'
    count_hit = True
    context_object_name = "question"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(QuestionDetail, self).get_context_data()
        context['categories'] = Category.objects.all()
        context['no_category_question_count'] = Question.objects.filter(category_id=None).count()
        context['answer_form'] = AnswerForm

        # 신고 관련 데이터 같이 삽입
        context['report_classes'] = Report_Class.objects.all().values_list('pk', 'name')
        context['report_form'] = ReportForm

        context['comment_form'] = CommentForm
        return context


# 작동 문제 없음
class QuestionCreate(LoginRequiredMixin, CreateView, ABC):
    model = Question
    form_class = QuestionForm
    template_name = 'question/question_form.html'

    def form_valid(self, form):
        current_user = self.request.user
        if current_user.is_authenticated:
            form.instance.user_id = current_user
            response = super(QuestionCreate, self).form_valid(form)
            tags = self.request.POST.get('tags')
            # print(tags)
            if tags:
                tags = tags.strip()
                tags = re.sub(r'[\s]', " ", tags)
                tags = tags.replace("#", " ")
                tags = tags.split()
                for t in tags:
                    t = t.strip()
                    # print(t)
                    tag, is_tag = Tag.objects.get_or_create(name=t)
                    # print(tag, is_tag)
                    # 없으면 생성, 있으면 생성값에
                    if is_tag:
                        tag.slug = slugify(t, allow_unicode=True)
                        tag.save()
                    tag.hit += 1
                    tag.save()
                    print(tag.hit + 1)
                    print(type(tag.hit))
                    self.object.tags.add(tag)
            ques_point_str = form.fields['ques_point']
            if ques_point_str:
                user = CustomUser.objects.get(username=current_user)
                if self.request.POST.get('ques_point') and int(user.left_ques()) > int(self.request.POST.get('ques_point')):
                    user.ques_point = str(int(user.left_ques()) - int(self.request.POST.get('ques_point')))
                    user.save()
                else:
                    return redirect('/question')
            return response
        else:
            return redirect('/question')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(QuestionCreate, self).get_context_data()
        context['categories'] = Category.objects.all()
        context['no_category_question_count'] = Question.objects.filter(category_id=None).count()
        return context


# 작동 문제 없음
class QuestionUpdate(LoginRequiredMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = 'question/question_update_form.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user == self.get_object().user_id:
            return super(QuestionUpdate, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super(QuestionUpdate, self).get_context_data()
        if self.object.tags.exists():
            tags_str = ""
            for t in self.object.tags.all():
                tags_str += ("#" + t.name + " ")
            print(tags_str)
            context['tags_str'] = tags_str
        return context

    def form_valid(self, form):
        current_user = self.request.user
        if current_user.is_authenticated:
            form.instance.user_id = current_user
            response = super(QuestionUpdate, self).form_valid(form)
            tags = self.request.POST.get('tags')
            # print(tags)
            if tags:
                tags = tags.strip()
                tags = re.sub(r'[\s]', " ", tags)
                tags = tags.replace("#", " ")
                tags = tags.split()
                for t in tags:
                    t = t.strip()
                    # print(t)
                    tag, is_tag = Tag.objects.get_or_create(name=t)
                    # print(tag, is_tag)
                    # 없으면 생성, 있으면 생성값에
                    if is_tag:
                        tag.slug = slugify(t, allow_unicode=True)
                        tag.save()
                    tag.hit += 1
                    tag.save()
                    self.object.tags.add(tag)
            ques_point_str = form.fields['ques_point']
            if ques_point_str:
                user = CustomUser.objects.get(username=current_user)
                if self.request.POST.get('ques_point') and int(user.left_ques()) > int(self.request.POST.get('ques_point')):
                    user.ques_point = str(int(user.left_ques()) - int(self.request.POST.get('ques_point')))
                    user.save()
                else:
                    return redirect('/question')
            return response
        else:
            return redirect('/question')


# 작동 문제 없음
class QuestionSearch(QuestionList):
    paginate_by = 8

    def get_queryset(self):
        q = self.kwargs['q']
        question_list = Question.objects.filter(
            Q(ques_title__contains=q)
            | Q(ques_desc__contains=q)
            | Q(category_id__slug__contains=q)
        ).distinct()
        return question_list

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(QuestionSearch, self).get_context_data()
        q = self.kwargs['q']
        context['search_info'] = f'Search : {q} ({self.get_queryset().count()}'
        return context


# 신고 접수 기능
def reportView(request, page_pk):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = ReportForm(data=request.POST)
            if form.is_valid():
                desc = form.cleaned_data.get('desc')
                user = request.user
                report_class = Report_Class.objects.get(pk=request.POST['report_class'])
                report_pk = request.POST['report_pk']
            else:
                messages.error(request, "신고 폼 형식이 맞지 않습니다.")
                return redirect('res', pk=page_pk)
            if request.POST['report_type'] == 'answer':
                report_pk = Answer.objects.get(pk=report_pk)
                if Report_Answer.objects.filter(report_user=user, report_answer=report_pk).exists():
                    messages.error(request, "이미 같은 게시글에 대한 신고를 하셨습니다.")
                    return redirect('res', pk=page_pk)
                report = Report_Answer(desc=desc, report_class=report_class, report_user=user,
                    report_answer=report_pk)
                report.save()
            elif request.POST['report_type'] == 'question':
                report_pk = Question.objects.get(pk=report_pk)
                if Report_Question.objects.filter(report_user=user, report_question=report_pk).exists():
                    messages.error(request, "이미 같은 게시글에 대한 신고를 하셨습니다.")
                    return redirect('res', pk=page_pk)
                report = Report_Question(desc=desc, report_class=report_class, report_user=user,
                    report_question=report_pk)
                report.save()
                
    messages.success(request, "신고가 접수 되었습니다.")
    return redirect('res', pk=page_pk)


def tag_page(request, slug):
    tag = Tag.objects.get(slug=slug)
    question_list = Question.objects.filter(tags=tag)

    return render(
        request,
        'question/question_list.html',
        {
            'object_list': question_list,
            'categories': Category.objects.all(),
            'no_category_question_count': Question.objects.filter(category_id=None).count(),
        }
    )