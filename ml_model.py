# -*- coding: utf-8 -*-
"""ML model.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1m4xed0PLU_a3ycowyCIHv_0MmqDvKQE_
"""

!ln -sf /opt/bin/nvidia-smi /usr/bin/nvidia-smi
!pip install gputil
!pip install psutil
!pip install humanize

import psutil
import humanize
import os
import GPUtil as GPU
GPUs = GPU.getGPUs()
# XXX: only one GPU on Colab and isn’t guaranteed
gpu = GPUs[0]
def printm():
    process = psutil.Process(os.getpid())
    print("Gen RAM Free: " + humanize.naturalsize( psutil.virtual_memory().available ), " | Proc size: " + humanize.naturalsize( process.memory_info().rss))
    print("GPU RAM Free: {0:.0f}MB | Used: {1:.0f}MB | Util {2:3.0f}% | Total {3:.0f}MB".format(gpu.memoryFree, gpu.memoryUsed, gpu.memoryUtil*100, gpu.memoryTotal))
printm()

import numpy as np
import seaborn as sns
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import os
import gc
import cv2
import matplotlib.pyplot as plt
from torchvision import transforms,datasets,models
from torch.utils.data import Dataset,DataLoader
from sklearn.model_selection import GroupKFold
from sklearn.metrics import accuracy_score,roc_auc_score
from sklearn.preprocessing import StandardScaler
import time
import datetime
from PIL import Image
import warnings
from tqdm.notebook import tqdm
import random
import pandas as pd

warnings.simplefilter('ignore')
torch.manual_seed(47)
np.random.seed(47)
random.seed(47)
torch.cuda.manual_seed(47)
torch.backends.cudnn.deterministic = True

from zipfile import ZipFile
import os
with ZipFile("/content/archive.zip", 'r') as zip_ref:
    zip_ref.extractall("/content/")

save_path = "./model_currency.pth"

path = '/content/Train'
image_path=[]
target=[]
for i in os.listdir(path):
    for j in os.listdir(os.path.join(path,i)):
        image_path.append(os.path.join(path,i,j))
        target.append(i)

table = {'image_path': image_path, 'target': target}
train_df = pd.DataFrame(data=table)
train_df = train_df.sample(frac = 1).reset_index(drop=True)

path = '/content/Test'
image_path=[]
target=[]
for i in os.listdir(path):
    for j in os.listdir(os.path.join(path,i)):
        image_path.append(os.path.join(path,i,j))
        target.append(i)

table = {'image_path': image_path, 'target': target}
test_df = pd.DataFrame(data=table)
test_df = test_df.sample(frac = 1).reset_index(drop=True)

train_df.head()

test_df.head()

label_mapping = {"5Hundrednote": 0,
                "1Hundrednote": 1,
                "2Hundrednote": 2,
                "Tennote": 3,
                "Fiftynote": 4,
                "Twentynote": 5,
                "2Thousandnote": 6}
train_df['target'] = train_df['target'].map(label_mapping).astype(int)
test_df['target'] = test_df['target'].map(label_mapping).astype(int)

plt.figure(figsize=(12, 12))
x = train_df.target.value_counts()
sns.barplot(x=x.index, y=x.values)  # Use keyword arguments
plt.gca().set_ylabel('Samples')

plt.figure(figsize=(12, 12))
x = test_df.target.value_counts()
sns.barplot(x=x.index, y=x.values)  # Use x and y as keyword arguments
plt.gca().set_ylabel('Samples')

class CustomDataset(Dataset):
    def __init__(self,dataframe,transform):
        self.dataframe = dataframe
        self.transform = transform
    def __len__(self):
        return self.dataframe.shape[0]
    def __getitem__(self,index):
        image = self.dataframe.iloc[index]['image_path']
        image = cv2.imread(image)
        image = cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        image = Image.fromarray(image)
        if self.transform:
            image = self.transform(image)
        label = int(self.dataframe.iloc[index]["target"])
        return {"image": torch.tensor(image, dtype=torch.float), "targets": torch.tensor(label, dtype = torch.long)}

def get_model(classes=7):
    model = models.resnet50(pretrained=True)
    features = model.fc.in_features
    model.fc = nn.Linear(in_features = features, out_features = classes)
    return model

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
device

model = get_model()
model.to(device)

train_transform = transforms.Compose([
    transforms.Resize((224,224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],std=[0.229, 0.224, 0.225])
])
test_transform = transforms.Compose([
    transforms.Resize((224,224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],std=[0.229, 0.224, 0.225])
])

optimizer  = optim.Adam(model.parameters(),lr = 0.00003)
loss_function = nn.CrossEntropyLoss()
train_dataset = CustomDataset(
dataframe=train_df,
transform=train_transform)
train_loader = DataLoader(train_dataset, batch_size = 16, shuffle = True, num_workers = 4)
valid_dataset = CustomDataset(
dataframe=test_df,
transform=test_transform)
valid_loader = DataLoader(valid_dataset, batch_size=16, shuffle=False, num_workers=4)
best_accuracy = 0

for epochs in tqdm(range(15),desc="Epochs"):
    model.train()
    for data_in_model in tqdm(train_loader, desc="Training"):
        inputs = data_in_model['image']
        target = data_in_model['targets']

        inputs = inputs.to(device, dtype = torch.float)
        targets = target.to(device, dtype = torch.long)

        optimizer.zero_grad()
        outputs = model(inputs)
        loss = loss_function(outputs,targets)
        loss.backward()
        optimizer.step()

    model.eval()
    final_targets = []
    final_outputs = []
    val_loss = 0
    with torch.no_grad():
        for data_in_model in tqdm(valid_loader, desc="Evaluating"):
            inputs = data_in_model['image']
            targets = data_in_model['targets']

            inputs = inputs.to(device, dtype = torch.float)
            targets = targets.to(device, dtype = torch.long)

            outputs = model(inputs)
            loss = loss_function(outputs, targets)
            val_loss += loss
            _,predictions = torch.max(outputs, 1)

            targets = targets.detach().cpu().numpy().tolist()
            predictions = predictions.detach().cpu().numpy().tolist()

            final_targets.extend(targets)
            final_outputs.extend(predictions)
    PREDS = np.array(final_outputs)
    TARGETS = np.array(final_targets)
    acc = (PREDS == TARGETS).mean() * 100
    if(acc>best_accuracy):
        best_accuracy = acc
        torch.save(model.state_dict(), save_path)
    print("EPOCH: {}/10".format(epochs+1))
    print("ACCURACY---------------------------------------------------->{}".format(acc))
    print("LOSS-------------------------------------------------------->{}".format(val_loss))

pip install numpy opencv-python scikit-learn

import os
import numpy as np
import cv2
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# Function to load images and labels from folders
def load_images_from_folder(folder_path):
    images = []
    labels = []

    for label in os.listdir(folder_path):  # Each subfolder is a class
        label_folder = os.path.join(folder_path, label)

        for filename in os.listdir(label_folder):
            img_path = os.path.join(label_folder, filename)
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)  # Grayscale images
            if img is not None:
                img_resized = cv2.resize(img, (64, 64))  # Resize to 64x64
                images.append(img_resized.flatten())  # Flatten to 1D
                labels.append(label)

    return np.array(images), np.array(labels)

# Load train and test data
train_folder_path = "/content/Train"
test_folder_path = "/content/Test"

X_train, y_train = load_images_from_folder(train_folder_path)
X_test, y_test = load_images_from_folder(test_folder_path)

# Encode the labels
label_encoder = LabelEncoder()
y_train_encoded = label_encoder.fit_transform(y_train)
y_test_encoded = label_encoder.transform(y_test)

# Standardize the data (important for SVM)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Train Decision Tree Classifier
dt_model = DecisionTreeClassifier(random_state=42)
dt_model.fit(X_train, y_train_encoded)
y_pred_dt = dt_model.predict(X_test)

# Train SVM Classifier
svm_model = SVC(kernel='linear', random_state=42)
svm_model.fit(X_train_scaled, y_train_encoded)
y_pred_svm = svm_model.predict(X_test_scaled)

# Evaluate Decision Tree
print("Decision Tree Accuracy:", accuracy_score(y_test_encoded, y_pred_dt))
print("Decision Tree Classification Report:\n", classification_report(y_test_encoded, y_pred_dt))
print("Decision Tree Confusion Matrix:\n", confusion_matrix(y_test_encoded, y_pred_dt))

# Evaluate SVM
print("SVM Accuracy:", accuracy_score(y_test_encoded, y_pred_svm))
print("SVM Classification Report:\n", classification_report(y_test_encoded, y_pred_svm))
print("SVM Confusion Matrix:\n", confusion_matrix(y_test_encoded, y_pred_svm))

pip install tensorflow opencv-python-headless scikit-learn





import os
import numpy as np
import cv2
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.decomposition import PCA

# Function to load images and labels from folders
def load_images_from_folder(folder_path, target_size=(128, 128)):
    images = []
    labels = []

    for label in os.listdir(folder_path):
        label_folder = os.path.join(folder_path, label)

        for filename in os.listdir(label_folder):
            img_path = os.path.join(label_folder, filename)
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                img_resized = cv2.resize(img, target_size)
                images.append(img_resized.flatten())
                labels.append(label)

    return np.array(images), np.array(labels)

# Load train and test data
train_folder_path = "/content/Train"
test_folder_path = "/content/Test"

X_train, y_train = load_images_from_folder(train_folder_path)
X_test, y_test = load_images_from_folder(test_folder_path)

# Encode labels
label_encoder = LabelEncoder()
y_train_encoded = label_encoder.fit_transform(y_train)
y_test_encoded = label_encoder.transform(y_test)

# Apply PCA to reduce dimensionality
pca = PCA(n_components=150)  # Keep 150 components
X_train_pca = pca.fit_transform(X_train)
X_test_pca = pca.transform(X_test)

# Standardize data
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_pca)
X_test_scaled = scaler.transform(X_test_pca)

# Define hyperparameters for non-linear SVM (RBF kernel)
param_grid = {
    'C': [0.1, 1, 10, 100],
    'gamma': [1e-3, 1e-4, 'scale'],
    'kernel': ['rbf']  # Using RBF kernel for non-linearity
}

# Perform hyperparameter tuning with GridSearchCV
svm_model = GridSearchCV(SVC(), param_grid, cv=3, n_jobs=-1, verbose=2)
svm_model.fit(X_train_scaled, y_train_encoded)

# Make predictions with the best model found
y_pred_svm = svm_model.predict(X_test_scaled)

# Evaluate the model
print("Best Parameters:", svm_model.best_params_)
print("SVM Accuracy:", accuracy_score(y_test_encoded, y_pred_svm))
print("SVM Classification Report:\n", classification_report(y_test_encoded, y_pred_svm))
print("SVM Confusion Matrix:\n", confusion_matrix(y_test_encoded, y_pred_svm))