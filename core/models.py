from django.db import models


class LegalEmailApplication(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('personal', 'Personal/Individual Use'),
        ('business', 'Business/Firm Use'),
    ]
    
    OCCUPATION_CHOICES = [
        ('lawyer', 'Lawyer'),
        ('judge', 'Judge'),
        ('legal_assistant', 'Legal Assistant'),
        ('law_student', 'Law Student'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    occupation = models.CharField(max_length=50, choices=OCCUPATION_CHOICES)
    lsk_admission_no = models.CharField(max_length=50, blank=True, null=True)
    current_email = models.EmailField()
    desired_email = models.CharField(max_length=100, help_text="Username part before @legal.ke")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.desired_email}@legal.ke"
