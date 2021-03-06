from django.shortcuts import render, redirect
# Create your views here.
from catalog.models import Item, Rate, User, Prediction
from django.views import generic
from catalog.forms import RateForm
from django.http import HttpResponse
import pandas as pd
from sklearn.model_selection import train_test_split
from surprise import Dataset
from surprise import Reader
from surprise.model_selection import cross_validate
from surprise import SVD
from surprise import BaselineOnly
from surprise.model_selection import cross_validate, KFold
from surprise.model_selection import GridSearchCV
from surprise import accuracy
from collections import defaultdict
from django.db import connections
import pickle


def index(request):
    """View function for home page of site."""

    item = Item.objects.all().count()
    user = User.objects.all().count()
    rate = Rate.objects.all().count()
    num_visits = request.session.get('num_visits', 1)
    request.session['num_visits'] = num_visits + 1

    context = {
        'item': item,
        'user': user,
        'rate': rate,
        'num_visits': num_visits,
    }

    # Render the HTML template index.html with the data in the context variable
    return render(request, 'index.html', context=context)


class ItemListView(generic.ListView):
    model = Item
    paginate_by = 10


class UserListView(generic.ListView):
    model = User
    paginate_by = 10


class RateListView(generic.ListView):
    model = Rate
    paginate_by = 20


class PredictionListView(generic.ListView):
    model = Prediction
    paginate_by = 20


def save_rate(request):
    if request.POST:
        print("okay")
        print(request.POST)
        if Rate.objects.filter(user_id=int(request.POST.get('content[user_id]')), item_id=int(request.POST.get('content[item_id]'))):
            print("이미 입력된 데이터입니다.")
            pass
        else:
            obj = Rate(user_id=int(request.POST.get('content[user_id]')),
                       item_id=int(request.POST.get('content[item_id]')),
                       rate=int(request.POST.get('content[rate]')))
            obj.save()
        print(request.POST.get('content[item_id]'))
        return render(request, "catalog/item_list.html")
    return HttpResponse(status=405)


def get_top_n(predictions, n=10, given_user_id=0):
    # First map the predictions to each user.
    with open("C:\\dev\\web_dev\\recoduct\\type_dict.pickle", 'rb') as f:
        type_dict = pickle.load(f)

    top_n = defaultdict(list)
    if given_user_id == 0:
        for uid, iid, true_r, est, _ in predictions:
            top_n[uid].append((iid, est))

        # Then sort the predictions for each user and retrieve the k highest ones.
        for uid, user_ratings in top_n.items():
            user_ratings.sort(key=lambda x: x[1], reverse=True)
            top_n[uid] = user_ratings[:n]
    else:
        user = User.objects.filter(user_id=given_user_id).values('skin_type')
        print(user)
        skin_type = user[0]['skin_type']
        minus_list = type_dict[skin_type]
        for uid, iid, true_r, est, _ in predictions:
            if uid == given_user_id:
                if iid in minus_list:
                    top_n[uid].append((iid, est - 1))
                else:
                    top_n[uid].append((iid, est))

        for uid, user_ratings in top_n.items():
            user_ratings.sort(key=lambda x: x[1], reverse=True)
            top_n[uid] = user_ratings[:n]

    return top_n


def recommend(given_user_id):
    given_user_id = int(given_user_id)
    queryset = Rate.objects.all()
    query, params = queryset.query.as_sql(compiler='django.db.backends.sqlite3.compiler.SQLCompiler', connection=connections['default'])
    df = pd.read_sql_query(query, con=connections['default'], params=params)
    print("load df")
    users = list(df['user_id'].value_counts()[lambda x: x >= 15].index)
    products = list(df['item_id'].value_counts()[lambda x: x > 20].index)
    new_df = df[(df['user_id'].isin(users)) & df['item_id'].isin(products)]
    reader = Reader(rating_scale=(1, 5))
    data = Dataset.load_from_df(new_df[['user_id', 'item_id', 'rate']], reader)
    trainset = data.build_full_trainset()
    testset = trainset.build_anti_testset()
    algo = SVD()
    algo.fit(trainset)
    print("fit 완료")
    predictions = algo.test(testset)
    print("예측 완료")
    top_10_items = get_top_n(predictions, 10, given_user_id)
    print("top 10 선별 완료, 길이 : %s" % len(list(top_10_items.keys())))
#    if given_user_id == 0:
#        for user_id, item_predictions in top_10_items.items():
#            for item_prediction in item_predictions:
#                obj = Prediction(user_id=user_id, item_id=item_prediction[0], prediction=item_prediction[1])
#                obj.save()
#        print("전체 유저에 대한 예측 저장 완료")
#        return [item_prediction[0] for user_id, item_predictions in top_10_items.items() for item_prediction in
#                item_predictions]
#    else:
    print(top_10_items[given_user_id])
    for item_prediction in top_10_items[given_user_id]:
        if Prediction.objects.filter(item_id=item_prediction[0], user_id=given_user_id):
            pass
        else:
            obj = Prediction(user_id=given_user_id, item_id=item_prediction[0], prediction=round(item_prediction[1], 1))
            obj.save()
    print("해당 유저 %s 에 대한 데이터 저장완료" % given_user_id)
    return [item_prediction[0] for item_prediction in top_10_items[given_user_id]]




def prediction(request):
    return render(request, "prediction.html")


def prediction_result(request):
    if request.session.get('user_id', False):
        user_id = request.session.get('user_id', False)
    item_id_list = recommend(user_id)
    print(item_id_list)
    predictions = Prediction.objects.filter(user_id=user_id).order_by('-prediction')
    items = Item.objects.filter(item_id__in=item_id_list)
    context = {
        'predictions': predictions,
        'items': items
    }
    return render(request, "prediction_result.html", context=context)


def sign_up(request):
    if request.POST:
        if User.objects.filter(user_id=int(request.POST.get('user_id'))):
            print("이미 입력된 데이터입니다.")
            return HttpResponse("이미 존재하는 유저 아이디 입니다. \n 다른 아이디를 입력해주세요 !<li><a href='sign_up_page'>다시 입력 하기</a></li>")
        else:
            obj = User(user_id=int(request.POST.get('user_id')),
                       skin_type=request.POST.get('skin_type'),
                       age=int(request.POST.get('age')),
                       gender=request.POST.get('gender'))
            obj.save()
            request.session['user_id'] = request.POST.get('user_id')
        return render(request, "catalog/sign_up.html")
    return HttpResponse(status=405)


def sign_up_page(request):
    return render(request, "catalog/sign_up.html")


def save_rate(request):
    if request.POST:
        print("okay")
        print(request.POST)
        if Rate.objects.filter(user_id=int(request.POST.get('content[user_id]')), item_id=int(request.POST.get('content[item_id]'))):
            pass
        else:
            obj = Rate(user_id=int(request.POST.get('content[user_id]')),
                       item_id=int(request.POST.get('content[item_id]')),
                       rate=int(request.POST.get('content[rate]')))
            obj.save()
        print(request.POST.get('content[item_id]'))
        return render(request, "catalog/item_list.html")
    return HttpResponse(status=405)



