from django.shortcuts import render, redirect
from mycollections import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from forms import *
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.urlresolvers import reverse
from models import *
from common.mongodb_repository import *
import logging
import pdb
import uuid

# Create your views here.
# this login required decorator is to not allow to any  
# view without authenticating
# @login_required(login_url="login/")
# def home(request):
# 	return render(request,"home.html")

def register(request, template_name, success_url='/'):
	if request.user.is_authenticated():
		return HttpResponseRedirect(reverse('home'))
	if request.method == 'POST':
		form = UserCreationForm(request.POST)
		#form.username = request.POST['email']
		if form.is_valid():
			email = form.cleaned_data['username']
			password = form.cleaned_data['password1']
			user = User.objects.create_user(username=email, email=email,password=password)
			user = authenticate(username=email,password=password)
			login(request, user)
			#return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
			return HttpResponseRedirect(reverse('home'))
		else:
			return render(request,template_name,{'form':form})
	else:
		form = UserCreationForm()
		return render(request, template_name, {'form': form})

def customLogin(request, template_name, authentication_form):
	if request.method == 'GET':
		if request.user.is_authenticated():
			return HttpResponseRedirect(reverse('home'))
		else:
			return render(request,template_name,{'authentication_form':authentication_form})
	else:
		return login(request)

@login_required(login_url="login/")
def get_collections(request):
	collections = list(Collection.objects.filter(user_id=request.user.id))
	return render(request, 'home.html', {'collections': collections})

@login_required(login_url="login/")
def create_collection(request, template_name, success_url):
	create = True
	if request.method == 'POST':
		collectionForm = CollectionForm(request.POST)
		if collectionForm.is_valid():
			collection = Collection.objects.create(user = request.user, name = collectionForm.cleaned_data['name'],
				description = collectionForm.cleaned_data['description'],
				isPrivate = collectionForm.cleaned_data['isPrivate'])
			#collection.save()
			return HttpResponseRedirect(success_url)
		else:
			pdb.set_trace()
			return render(request,template_name,{'collectionForm':collectionForm})
	else:
		collectionForm = CollectionForm()
		return render(request,template_name,{'collectionForm':collectionForm})

@login_required(login_url="login/")
def edit_collection(request, template_name, success_url, id):
	collection = Collection.objects.get(id=int(id))
	create = False
	if request.method == 'POST':
		collectionForm = CollectionForm(request.POST)
		#pdb.set_trace()
		if collectionForm.is_valid():
			collectionForm = CollectionForm(request.POST, instance = collection)
			collectionForm.save()
			#pdb.set_trace()
			return HttpResponseRedirect(success_url)
		else:
			#pdb.set_trace()
			return redirect(edit_collection,id)
	else:
		collectionForm = CollectionForm(instance=collection)
		#pdb.set_trace()
		return render(request, template_name, {'collectionForm':collectionForm})

@login_required(login_url="login/")
def list_collection_items(request, template_name, id):
	collection = Collection.objects.get(id=int(id))
	collectionItems = list(collection.collectionItems.all())

	itemsRepository = MongoDbItemsRepository()
	items = itemsRepository.get_items(collection.name + str(collection.id))
	
	for item in collectionItems:
		item.customFields = {}
		mongoitem = [x for x in items if str(x["uuid"])==item.identifier][0]
		for k,v in mongoitem.iteritems():
			if k == "_id" or k =="uuid" or k == "collectionId":
				continue
			item.customFields[k]=v
	
	return render(request, template_name,{'collection':collection, "collectionItems":collectionItems})

@login_required(login_url="login/")
def add_collection_item(request,id, template_name='add_item.html', success_url='/'):
	collection = Collection.objects.get(id=int(id))
	if request.method == 'POST':
		data = request.POST
		
		#Insert in sql name and description
		collectionItem = CollectionItem.objects.create(name=data["name"],description=data["description"],identifier=uuid.uuid4())
		collectionItem.save()
		collection.collectionItems.add(collectionItem)
		collection.save()

		#insert custom fields in mongodb and update the list of custom fields on the collection
		customFields = {}
		d = { 'uuid':collectionItem.identifier, 'collectionId' : collection.id }
		for k in data:
			if k=="name" or k=="description" or k=="id" or k.endswith("_type"):
				continue
			d[k]=data[k]
			customFields[k] = data[k + "_type"]

		add_custom_fields(customFields, collection)

		itemsRepository = MongoDbItemsRepository()
		itemsRepository.insert_item(collection.name + str(collection.id), d)
		
		return JsonResponse(data)
	else:
		customFields = [(k,v,field_type_value_to_field_type_name(int(v))) for k,v in get_collection_fields(collection).iteritems()]
		return render(request, template_name, {"collection":collection, "customFields": customFields})

def edit_item(request,collectionId,itemId,template_name='add_item.html',success_url='/'):
	collection = Collection.objects.get(id=int(collectionId))
	customFields = [(k,v,field_type_value_to_field_type_name(int(v))) for k,v in get_collection_fields(collection).iteritems()]
	collectionItem = CollectionItem.objects.get(id=int(itemId))
	itemForm = ItemForm(instance=collectionItem)
	print itemForm
	return render(request, template_name,{"collection":collection, "customFields": customFields, "itemForm": itemForm})

@login_required(login_url="login/")
def delete(request):
	pass

def add_custom_fields(customFields, collection):
	collectionFields = get_collection_fields(collection)

	newFields = {}
	for k in customFields:
		if collectionFields.has_key(k):
			continue
		newFields[k] = customFields[k]
	#print newFields
	if len(newFields) == 0:
		return
	arr = []
	for k in newFields:
		arr.append(k)
		arr.append(newFields[k])

	if len(collection.itemCustomFields) > 0:
		collection.itemCustomFields += "," + ",".join(arr)
	else:
		collection.itemCustomFields += ",".join(arr)

	collection.save()

def get_collection_fields(collection):
	collectionFields = {}
	if len(collection.itemCustomFields.strip()) > 0:
		cfArr = collection.itemCustomFields.split(',')
 		for i in range(0,len(cfArr),2):
			collectionFields[cfArr[i]] = cfArr[i+1]
	return collectionFields

def field_type_value_to_field_type_name(fieldTypeValue):
	if fieldTypeValue == 1:
		return 'Number'
	elif fieldTypeValue == 2:
		return 'Date'
	else:
		return 'Text'
